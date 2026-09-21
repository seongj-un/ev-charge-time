"""한국환경공단 전기자동차 충전소 정보 API 클라이언트 (F-07).

https://www.data.go.kr/data/15076352/openapi.do

**이 모듈은 라우터에서 쓰지 않는다.** 개발계정 트래픽이 하루 1,000건이라
사용자 요청마다 부르면 즉시 넘친다. 수집기(``charger_sync``)만 이 클라이언트를
쓰고, ``GET /api/chargers``는 수집기가 채운 공유 캐시만 읽는다.

응답 봉투는 2026-09-21에 실제 호출로 확인했다 — 포털 문서가 흔히 보여주는
``response.header``/``response.body`` 2단 구조가 아니라 평평하다::

    {"items": {"item": [...]}, "resultCode": "00", "resultMsg": "NORMAL SERVICE.",
     "totalCount": 32835, "pageNo": 1, "numOfRows": 10}

``dataType``은 **대문자 JSON**이어야 한다. 소문자 ``json``을 보내면 XML이 온다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/B552584/EvCharger/"
OK_RESULT_CODE = "00"

# 충전소 상세(getChargerInfo)는 한 번에 크게 받는 편이 호출 수를 아낀다.
# zcode=12가 32,835건이라 9999면 4페이지다.
DEFAULT_PAGE_SIZE = 9999

# 페이지 상한. totalCount와 실제 행 수가 어긋나도 무한히 부르지 않게 한다.
# 9999행 × 50 = 약 50만 행으로, 전국(524,903건)을 한 번에 받아도 넘지 않는다.
MAX_PAGES = 50


class ChargerApiError(RuntimeError):
    """공공 API 호출 실패. 문구에 서비스키가 절대 들어가지 않는다."""


@dataclass
class ChargerApiClient:
    """충전소 API 호출기. 페이지네이션까지 안에서 끝낸다.

    재시도는 **네트워크 오류와 5xx에만** 건다. 4xx나 ``resultCode != "00"``은
    다시 불러도 같은 답이고(키 오류·잘못된 파라미터), 실패한 호출도 하루
    1,000건 할당량을 깎기 때문이다.
    """

    service_key: str
    base_url: str = BASE_URL
    # (연결, 읽기) 모두 넉넉히. 9999행 한 페이지가 수 MB라 읽기가 길다.
    timeout: float = 30.0
    max_attempts: int = 3
    retry_wait_s: float = 1.0
    page_size: int = DEFAULT_PAGE_SIZE
    # 테스트에서 httpx.MockTransport를 물리는 자리. 운영에서는 None이다.
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def fetch_station_rows(self, zcode: str) -> list[dict]:
        """``getChargerInfo`` — 충전소+충전기 상세. **충전기 1대당 1행**이다."""
        return self._fetch_all_pages("getChargerInfo", {"zcode": zcode})

    def fetch_status_rows(self, zcode: str, period: int) -> list[dict]:
        """``getChargerStatus`` — 상태만. ``period``(1~10분) 안에 바뀐 것만 온다.

        전체 재수집보다 훨씬 싸다(zcode=12, period=10에 964건).
        """
        return self._fetch_all_pages("getChargerStatus", {"zcode": zcode, "period": period})

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _fetch_all_pages(self, operation: str, params: dict) -> list[dict]:
        """``totalCount``를 다 모을 때까지 페이지를 넘긴다.

        ``numOfRows``로 페이지 수를 계산하지 않는 이유: 이 API는 요청한 값이
        아니라 **그 페이지에 실제로 담긴 행 수**를 돌려준다(마지막 페이지는
        9999가 아니라 2838). 그걸 페이지 크기로 믿고 곱하면 한 바퀴를 더 돌아
        빈 페이지를 받는다 — 실측으로 4페이지면 될 것을 5번 불렀다. 하루
        1,000건 예산에서 호출 한 건은 그냥 한 건이다.

        빈 페이지와 페이지 상한은 무한 루프를 막는 안전장치다.
        """
        rows: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            payload = self._request(operation, {**params, "pageNo": page})
            page_rows = _items(payload)
            rows.extend(page_rows)

            total = _as_int(payload.get("totalCount"))
            if not page_rows or total is None or len(rows) >= total:
                return rows

        logger.warning("%s 페이지 상한(%d)에 걸려 중단한다", operation, MAX_PAGES)
        return rows

    def _request(self, operation: str, params: dict) -> dict:
        query = {
            "serviceKey": self.service_key,
            "numOfRows": self.page_size,
            # 대문자여야 JSON이 온다.
            "dataType": "JSON",
            **params,
        }
        url = f"{self.base_url.rstrip('/')}/{operation}"

        last_error: str = "알 수 없는 오류"
        for attempt in range(1, self.max_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                    response = client.get(url, params=query)
            except httpx.TransportError as exc:
                # 연결 실패·타임아웃. 예외 문구에 URL(=serviceKey)이 실리므로 가린다.
                last_error = f"{operation} 연결 실패: {self._mask(str(exc))}"
            else:
                if response.status_code >= 500:
                    last_error = f"{operation} 서버 오류 {response.status_code}"
                elif response.status_code >= 400:
                    # 다시 불러도 같은 답이다. 재시도하지 않는다.
                    raise ChargerApiError(
                        f"{operation} 요청 거부 {response.status_code}: "
                        f"{self._mask(response.text[:200])}"
                    )
                else:
                    return self._parse(operation, response.text)

            if attempt < self.max_attempts:
                time.sleep(self.retry_wait_s * attempt)

        raise ChargerApiError(f"{operation} 실패({self.max_attempts}회 시도): {last_error}")

    def _parse(self, operation: str, text: str) -> dict:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            # 포털 점검 공지나 인증 실패는 JSON 대신 XML/HTML로 온다.
            raise ChargerApiError(
                f"{operation} 응답이 JSON이 아니다: {self._mask(text[:200])}"
            ) from exc

        if not isinstance(payload, dict):
            raise ChargerApiError(f"{operation} 응답 형식이 예상과 다르다")

        code = str(payload.get("resultCode", ""))
        if code != OK_RESULT_CODE:
            message = self._mask(str(payload.get("resultMsg", "")))
            raise ChargerApiError(f"{operation} resultCode={code}: {message}")

        return payload

    def _mask(self, text: str) -> str:
        """응답 본문·예외 문구에 되비쳐 나온 서비스키를 지운다.

        포털은 인증 오류 본문에 보낸 키를 그대로 실어 준다. 그게 로그나 에러
        트래킹으로 새면 키가 공개된다.
        """
        if not self.service_key:
            return text
        return text.replace(self.service_key, "<SERVICE_KEY>")


def _items(payload: dict) -> list[dict]:
    """``items.item``을 항상 리스트로 꺼낸다.

    포털 API는 결과가 0건이면 ``items``가 빈 문자열, 1건이면 ``item``이 리스트가
    아니라 객체로 오는 일이 잦다. 호출자가 그 변덕을 알 필요는 없다.
    """
    items = payload.get("items")
    if isinstance(items, dict):
        items = items.get("item")
    if isinstance(items, dict):
        return [items]
    if isinstance(items, list):
        return [row for row in items if isinstance(row, dict)]
    return []


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
