"""기상청 단기예보 조회서비스 클라이언트 (F-09).

공공데이터포털 데이터 번호 **15084084** (``기상청_단기예보 조회서비스``)
``VilageFcstInfoService_2.0/getVilageFcst``.

``infra/charger_api.py``와 같은 모양이다 — 주입 가능한 ``transport``로 테스트가
실제 API를 부르지 않게 하고, 재시도는 네트워크 오류와 5xx에만 걸며, 예외 문구에서
서비스키를 가린다.

개발계정 일일 10,000건으로 충전소 API(1,000건)보다 여유롭지만, 예보는 하루 여덟
번만 갱신되므로 사용자 요청마다 부르는 것은 낭비다. 캐시는
``api/solar_service.py``가 발표 단위로 들고 있다.

──────────────────────────────────────────────────────────────────────────
2026-09-21 실제 호출로 확인한 것 (활용가이드 문서 없이 실측으로 확정했다)
──────────────────────────────────────────────────────────────────────────

**1. 응답 봉투가 충전소 API와 다르다.** 이쪽은 ``response.header`` /
``response.body`` 2단 구조다::

    {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                  "body": {"items": {"item": [...]}, "totalCount": 1016, ...}}}

충전소 API의 평평한 봉투를 그대로 기대하면 ``items``를 못 찾아 조용히 0건이 된다.

**2. 발표 시각은 여덟 개뿐이다.** 0200·0500·0800·1100·1400·1700·2000·2300만
데이터를 준다. 2100·2200·0000·0100·0300은 ``resultCode=03`` (NO_DATA)였다 —
즉 API가 가까운 발표로 알아서 맞춰 주지 않는다. 잘못 고르면 빈 응답이다.

**3. 가장 최근 발표는 잠시 '반쯤 쓰인' 상태로 온다.** 22:10 KST에
``base_time=2300``을 반복 호출하니 같은 요청이 ``totalCount`` 408행과 980행을
번갈아 돌려줬다 — **둘 다 ``resultCode=00``** 이었다. 안정된 발표(2000)는 같은
시각에 1016행으로 일정했다. 그래서 ``PUBLISH_SETTLE`` 만큼 지난 발표만 쓰고,
그래도 구멍이 있으면 호출자가 이전 발표로 물러선다. "오류 없이 일부만 온다"가
가장 위험한 실패 모양이라 여기에 특히 신경 썼다.

**4. 시간별(1시간 간격) 자료는 발표일+2일까지다.** 그 뒤로는 3시간 간격으로
띄엄띄엄 오고 4일째에 끝난다. 하루 24시간이 온전히 채워지는 것은 '내일'과
'모레'뿐이고, '오늘'은 발표 시각 이후 시간대만 있다.

**5. 과거 발표분은 최소 5주 뒤에도 조회된다** (2026-08-15 발표분 조회 성공).

**6. HTTPS로 접속된다.** 포털 예제는 ``http``지만 ``https``도 같은 응답을 준다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/"
OK_RESULT_CODE = "00"
NO_DATA_RESULT_CODE = "03"

# 실측으로 데이터를 돌려준 발표 시각(그 밖은 전부 NO_DATA).
BASE_TIMES: tuple[str, ...] = ("0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300")

# 발표 시각으로부터 이만큼 지나야 그 발표를 쓴다.
#
# 공식 발표는 매 발표시각 +10분이지만, 위 3번에서 본 대로 그 무렵에는 응답이
# 반쯤 쓰인 상태로 올 수 있다. 45분은 발표(+10분) 뒤로 충분히 여유를 두면서도
# 발표 간격(3시간)보다 훨씬 짧아, 항상 안정된 발표가 하나는 있게 한다.
PUBLISH_SETTLE = timedelta(minutes=45)

# 한 발표는 실측 최대 1,052행이다. 2,000이면 한 번의 호출로 다 받는다.
DEFAULT_PAGE_SIZE = 2000

# totalCount와 실제 행 수가 어긋나도(위 3번) 무한히 부르지 않게 한다.
MAX_PAGES = 5


class KmaApiError(RuntimeError):
    """기상청 API 호출 실패. 문구에 서비스키가 절대 들어가지 않는다."""


class KmaNoDataError(KmaApiError):
    """``resultCode=03`` — 그 발표(또는 그 격자)에 자료가 없다.

    장애가 아니라 '아직/이미 없다'는 뜻이라 별도 예외로 둔다. 호출자는 이걸
    보고 이전 발표로 물러선다.
    """


def latest_settled_base_time(now: datetime) -> tuple[str, str]:
    """``now`` 기준으로 안정적으로 쓸 수 있는 가장 최근 발표 ``(base_date, base_time)``.

    발표 시각 + ``PUBLISH_SETTLE``이 지난 것 중 가장 최근을 고른다. 오늘 것이
    아직 하나도 자리잡지 않았으면 (예: 새벽 01시) 전날 2300으로 넘어간다.
    """
    today = now.date()
    for base_time in reversed(BASE_TIMES):
        issued = now.replace(
            hour=int(base_time[:2]), minute=int(base_time[2:]), second=0, microsecond=0
        )
        if now - issued >= PUBLISH_SETTLE:
            return today.strftime("%Y%m%d"), base_time

    # 오늘 발표가 아직 하나도 자리잡지 않았다 — 전날 마지막 발표.
    yesterday = today - timedelta(days=1)
    return yesterday.strftime("%Y%m%d"), BASE_TIMES[-1]


def previous_issuance(base_date: str, base_time: str) -> tuple[str, str]:
    """바로 이전 발표. 자정을 넘으면 전날 마지막 발표로 간다."""
    index = BASE_TIMES.index(base_time)
    if index > 0:
        return base_date, BASE_TIMES[index - 1]

    day = datetime.strptime(base_date, "%Y%m%d").date() - timedelta(days=1)
    return day.strftime("%Y%m%d"), BASE_TIMES[-1]


@dataclass
class KmaApiClient:
    """단기예보 호출기.

    재시도는 **네트워크 오류와 5xx에만** 건다. 4xx나 ``resultCode != "00"``은
    다시 불러도 같은 답이고(키 오류·잘못된 파라미터), 실패한 호출도 일일
    할당량을 깎는다.
    """

    service_key: str
    base_url: str = BASE_URL
    timeout: float = 20.0
    max_attempts: int = 3
    retry_wait_s: float = 1.0
    page_size: int = DEFAULT_PAGE_SIZE
    # 테스트에서 httpx.MockTransport를 물리는 자리. 운영에서는 None이다.
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def fetch_village_forecast(
        self, nx: int, ny: int, base_date: str, base_time: str
    ) -> list[dict]:
        """한 발표의 예보 행 전부. 행 하나 = (예보시각, 항목) 하나다.

        ``totalCount``를 다 모을 때까지 페이지를 넘기지만, 기본 페이지 크기가
        한 발표보다 크므로 정상 경로에서는 호출이 한 번이다.
        """
        rows: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            payload = self._request(
                {
                    "nx": nx,
                    "ny": ny,
                    "base_date": base_date,
                    "base_time": base_time,
                    "pageNo": page,
                }
            )
            page_rows = _items(payload)
            rows.extend(page_rows)

            total = _as_int(payload.get("totalCount"))
            if not page_rows or total is None or len(rows) >= total:
                return rows

        logger.warning("단기예보 페이지 상한(%d)에 걸려 중단한다", MAX_PAGES)
        return rows

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _request(self, params: dict) -> dict:
        query = {
            "serviceKey": self.service_key,
            "numOfRows": self.page_size,
            # 충전소 API와 마찬가지로 대문자여야 JSON이 온다.
            "dataType": "JSON",
            **params,
        }
        url = f"{self.base_url.rstrip('/')}/getVilageFcst"

        last_error = "알 수 없는 오류"
        for attempt in range(1, self.max_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                    response = client.get(url, params=query)
            except httpx.TransportError as exc:
                # 예외 문구에 URL(=serviceKey)이 실리므로 가린다.
                last_error = f"단기예보 연결 실패: {self._mask(str(exc))}"
            else:
                if response.status_code >= 500:
                    last_error = f"단기예보 서버 오류 {response.status_code}"
                elif response.status_code >= 400:
                    # 다시 불러도 같은 답이다.
                    raise KmaApiError(
                        f"단기예보 요청 거부 {response.status_code}: "
                        f"{self._mask(response.text[:200])}"
                    )
                else:
                    return self._parse(response.text)

            if attempt < self.max_attempts:
                time.sleep(self.retry_wait_s * attempt)

        raise KmaApiError(f"단기예보 실패({self.max_attempts}회 시도): {last_error}")

    def _parse(self, text: str) -> dict:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            # 포털 점검 공지나 인증 실패는 JSON 대신 XML/HTML로 온다.
            raise KmaApiError(f"단기예보 응답이 JSON이 아니다: {self._mask(text[:200])}") from exc

        if not isinstance(payload, dict):
            raise KmaApiError("단기예보 응답 형식이 예상과 다르다")

        # 2단 봉투(response.header / response.body). 충전소 API와 다른 지점이다.
        envelope = payload.get("response")
        if not isinstance(envelope, dict):
            raise KmaApiError("단기예보 응답에 response 봉투가 없다")

        header = envelope.get("header") or {}
        code = str(header.get("resultCode", ""))
        message = self._mask(str(header.get("resultMsg", "")))

        if code == NO_DATA_RESULT_CODE:
            raise KmaNoDataError(f"단기예보 자료 없음(resultCode=03): {message}")
        if code != OK_RESULT_CODE:
            raise KmaApiError(f"단기예보 resultCode={code}: {message}")

        body = envelope.get("body")
        return body if isinstance(body, dict) else {}

    def _mask(self, text: str) -> str:
        """응답 본문·예외 문구에 되비쳐 나온 서비스키를 지운다."""
        if not self.service_key:
            return text
        return text.replace(self.service_key, "<SERVICE_KEY>")


def _items(body: dict) -> list[dict]:
    """``items.item``을 항상 리스트로 꺼낸다.

    포털 API는 결과가 0건이면 ``items``가 빈 문자열, 1건이면 ``item``이
    리스트가 아니라 객체로 오는 일이 잦다.
    """
    items = body.get("items")
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
