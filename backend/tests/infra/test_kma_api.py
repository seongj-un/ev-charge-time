"""기상청 단기예보 API 클라이언트.

**이 테스트는 절대 실제 API를 부르지 않는다.** ``httpx.MockTransport``로 고정
응답을 물려 검증한다 — 충전소 클라이언트(``test_charger_api.py``)와 같은 방식이고,
우리 코드가 만든 요청(URL·쿼리·재시도)까지 그대로 볼 수 있다.

응답 봉투 모양·``resultCode`` 값·발표 시각은 2026-09-21에 실제 호출로 확인한
것을 따른다. 그 실측 내용은 ``infra/kma_api.py``의 독스트링에 적어 두었다.
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest

from evcharge.domain.pricing import KST
from evcharge.infra.kma_api import (
    BASE_TIMES,
    KmaApiClient,
    KmaApiError,
    KmaNoDataError,
    latest_settled_base_time,
    previous_issuance,
)

KEY = "test-kma-service-key-1234"


def _item(category: str, value: str, fcst_date: str = "20260922", fcst_time: str = "1200") -> dict:
    return {
        "baseDate": "20260921",
        "baseTime": "2000",
        "category": category,
        "fcstDate": fcst_date,
        "fcstTime": fcst_time,
        "fcstValue": value,
        "nx": 56,
        "ny": 71,
    }


def _body(
    items: list[dict], *, code: str = "00", msg: str = "NORMAL_SERVICE",
    total: int | None = None,
) -> str:
    """실제 응답 봉투. **충전소 API와 달리 ``response.header``/``body``로 감싼다.**

    2026-09-21 실측으로 확인했다. 충전소 API의 평평한 봉투를 그대로 기대하면
    ``items``를 못 찾아 빈 목록이 된다.
    """
    if code != "00":
        return json.dumps({"response": {"header": {"resultCode": code, "resultMsg": msg}}})
    return json.dumps(
        {
            "response": {
                "header": {"resultCode": code, "resultMsg": msg},
                "body": {
                    "dataType": "JSON",
                    "items": {"item": items},
                    "pageNo": 1,
                    "numOfRows": len(items),
                    "totalCount": total if total is not None else len(items),
                },
            }
        }
    )


def _client(handler, **kwargs) -> KmaApiClient:
    return KmaApiClient(
        service_key=KEY, transport=httpx.MockTransport(handler), retry_wait_s=0, **kwargs
    )


# ── 요청 모양 ────────────────────────────────────────────────────────────


def test_sends_uppercase_json_and_the_grid_coordinates():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=_body([_item("SKY", "1")]))

    _client(handler).fetch_village_forecast(nx=56, ny=71, base_date="20260921", base_time="2000")

    assert len(seen) == 1
    params = seen[0].url.params
    assert params["dataType"] == "JSON"
    assert params["nx"] == "56"
    assert params["ny"] == "71"
    assert params["base_date"] == "20260921"
    assert params["base_time"] == "2000"
    assert params["serviceKey"] == KEY


def test_parses_the_nested_response_envelope():
    """``response.body.items.item``에서 행을 꺼낸다 (충전소 API와 다른 모양)."""
    rows = _client(
        lambda _r: httpx.Response(200, text=_body([_item("SKY", "3"), _item("PTY", "1")]))
    ).fetch_village_forecast(nx=56, ny=71, base_date="20260921", base_time="2000")

    assert [(r["category"], r["fcstValue"]) for r in rows] == [("SKY", "3"), ("PTY", "1")]


# ── resultCode 처리 ──────────────────────────────────────────────────────


def test_no_data_is_its_own_error_so_the_caller_can_fall_back():
    """``resultCode=03``(NO_DATA)은 장애가 아니라 '그 발표는 아직 없다'는 뜻이다.

    실측: 발표 시각이 아닌 base_time(2100, 0000 등)과 미래 날짜는 전부 03이다.
    이걸 일반 오류와 같이 취급하면 이전 발표로 물러설 수가 없다.
    """
    with pytest.raises(KmaNoDataError):
        _client(
            lambda _r: httpx.Response(200, text=_body([], code="03", msg="NO_DATA"))
        ).fetch_village_forecast(nx=56, ny=71, base_date="20260922", base_time="0200")


def test_other_result_codes_raise_the_general_error():
    with pytest.raises(KmaApiError) as excinfo:
        _client(
            lambda _r: httpx.Response(
                200, text=_body([], code="30", msg="SERVICE_KEY_IS_NOT_REGISTERED_ERROR")
            )
        ).fetch_village_forecast(nx=56, ny=71, base_date="20260921", base_time="2000")

    assert not isinstance(excinfo.value, KmaNoDataError)


def test_no_data_error_is_a_kma_api_error():
    """호출자가 '기상청 관련 실패'를 한 번에 잡을 수 있어야 한다."""
    assert issubclass(KmaNoDataError, KmaApiError)


def test_the_service_key_never_leaks_into_an_error_message():
    """포털은 인증 오류 본문에 보낸 키를 그대로 실어 준다. 로그로 새면 안 된다."""
    with pytest.raises(KmaApiError) as excinfo:
        _client(
            lambda _r: httpx.Response(200, text=_body([], code="30", msg=f"bad key: {KEY}"))
        ).fetch_village_forecast(nx=56, ny=71, base_date="20260921", base_time="2000")

    assert KEY not in str(excinfo.value)
    assert "<SERVICE_KEY>" in str(excinfo.value)


def test_non_json_response_is_reported_clearly():
    """포털 점검 공지·인증 실패는 JSON 대신 XML/HTML로 온다."""
    with pytest.raises(KmaApiError):
        _client(
            lambda _r: httpx.Response(
                200, text="<OpenAPI_ServiceResponse>…</OpenAPI_ServiceResponse>"
            )
        ).fetch_village_forecast(nx=56, ny=71, base_date="20260921", base_time="2000")


# ── 재시도 ───────────────────────────────────────────────────────────────


def test_retries_server_errors_then_succeeds():
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, text=_body([_item("SKY", "1")]))

    rows = _client(handler).fetch_village_forecast(
        nx=56, ny=71, base_date="20260921", base_time="2000"
    )

    assert calls["n"] == 3
    assert len(rows) == 1


def test_client_errors_are_not_retried():
    """4xx는 다시 불러도 같은 답이다. 실패한 호출도 일일 할당량을 깎는다."""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(KmaApiError):
        _client(handler).fetch_village_forecast(
            nx=56, ny=71, base_date="20260921", base_time="2000"
        )

    assert calls["n"] == 1


# ── 발표 시각 선택 ───────────────────────────────────────────────────────


def test_base_times_are_the_eight_observed_issuances():
    """실측으로 데이터를 돌려준 발표 시각은 이 여덟 개뿐이다.

    2100·2200·0000·0100·0300은 전부 NO_DATA였다.
    """
    assert BASE_TIMES == ("0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300")


@pytest.mark.parametrize(
    "now,expected",
    [
        # 22:10 — 2300 발표는 아직 안정되지 않았다(실측에서 이 시각의 2300은
        # 같은 요청에 408행/980행을 번갈아 돌려줬다). 2000을 쓴다.
        (datetime(2026, 9, 21, 22, 10, tzinfo=KST), ("20260921", "2000")),
        # 23:50 — 2300 발표가 자리잡은 뒤
        (datetime(2026, 9, 21, 23, 50, tzinfo=KST), ("20260921", "2300")),
        # 자정 직후 — 전날 2300으로 넘어간다
        (datetime(2026, 9, 22, 0, 30, tzinfo=KST), ("20260921", "2300")),
        # 02:40 — 0200 발표(+45분)가 아직이다
        (datetime(2026, 9, 22, 2, 40, tzinfo=KST), ("20260921", "2300")),
        # 02:50 — 0200 발표가 자리잡았다
        (datetime(2026, 9, 22, 2, 50, tzinfo=KST), ("20260922", "0200")),
        (datetime(2026, 9, 22, 14, 44, tzinfo=KST), ("20260922", "1100")),
        (datetime(2026, 9, 22, 14, 46, tzinfo=KST), ("20260922", "1400")),
    ],
)
def test_picks_the_latest_settled_issuance(now, expected):
    assert latest_settled_base_time(now) == expected


def test_previous_issuance_walks_backwards_across_midnight():
    assert previous_issuance("20260922", "0500") == ("20260922", "0200")
    assert previous_issuance("20260922", "0200") == ("20260921", "2300")
    assert previous_issuance("20260921", "2300") == ("20260921", "2000")
