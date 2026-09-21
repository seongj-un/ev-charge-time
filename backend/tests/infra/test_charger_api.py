"""공공데이터포털 충전소 API 클라이언트.

**이 테스트는 절대 실제 API를 부르지 않는다.** 개발계정 트래픽이 하루 1,000건이라
테스트가 그걸 갉아먹으면 시연 당일에 할당량이 없다. ``httpx.MockTransport``로
고정 응답을 물려 검증한다 — 우리 코드가 만든 요청(URL·쿼리·재시도)까지 그대로
볼 수 있어서 가짜 클라이언트를 따로 만드는 것보다 검증 범위가 넓다.
"""

from __future__ import annotations

import json

import httpx
import pytest

from evcharge.infra.charger_api import MAX_PAGES, ChargerApiClient, ChargerApiError

KEY = "test-service-key-1234"


def _row(stat_id: str, chger_id: str) -> dict:
    return {"statId": stat_id, "chgerId": chger_id, "statNm": "테스트 충전소"}


def _body(items: list[dict], *, total: int, page: int, rows: int = 10) -> str:
    """실제 응답 봉투 모양. 2026-09-21에 getChargerInfo를 한 번 호출해 확인했다:
    ``{"items": {"item": [...]}, "resultCode", "resultMsg", "totalCount",
    "pageNo", "numOfRows"}`` — ``response.header``/``body``로 감싸지 않는다."""
    return json.dumps(
        {
            "items": {"item": items},
            "resultCode": "00",
            "resultMsg": "NORMAL SERVICE.",
            "totalCount": total,
            "pageNo": page,
            "numOfRows": rows,
        }
    )


def _client(handler, **kwargs) -> ChargerApiClient:
    # retry_wait_s=0: 재시도 동작은 검증하되 테스트가 실제로 잠들지는 않게.
    return ChargerApiClient(
        service_key=KEY, transport=httpx.MockTransport(handler), retry_wait_s=0, **kwargs
    )


def test_sends_uppercase_json_datatype_and_the_service_key():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=_body([_row("ST-1", "01")], total=1, page=1))

    _client(handler).fetch_station_rows("12")

    assert len(seen) == 1
    params = seen[0].url.params
    # 소문자 json이면 XML이 온다. 대문자 JSON이어야 한다.
    assert params["dataType"] == "JSON"
    assert params["serviceKey"] == KEY
    assert params["zcode"] == "12"
    assert seen[0].url.path.endswith("/getChargerInfo")


def test_follows_pagination_until_every_row_is_collected():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pageNo"])
        items = [_row(f"ST-{page}-{i}", "01") for i in range(10 if page < 3 else 2)]
        return httpx.Response(200, text=_body(items, total=22, page=page))

    rows = _client(handler, page_size=10).fetch_station_rows("12")

    # 3페이지(10+10+2)를 클라이언트가 알아서 다 돌아야 한다.
    assert len(rows) == 22
    assert rows[0]["statId"] == "ST-1-0"
    assert rows[-1]["statId"] == "ST-3-1"


def test_stops_as_soon_as_every_row_is_collected():
    """마지막 페이지를 받고 한 바퀴 더 돌지 않는다.

    이 API는 numOfRows에 요청값이 아니라 **그 페이지의 실제 행 수**를 실어
    준다(마지막 페이지는 9999가 아니라 2838). 그걸 페이지 크기로 믿고 곱해
    끝을 판단하면 4페이지면 될 것을 5번 부른다 — 실측으로 겪었다.
    """
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pageNo"])
        pages.append(page)
        count = 10 if page == 1 else 2
        items = [_row(f"ST-{page}-{i}", "01") for i in range(count)]
        return httpx.Response(200, text=_body(items, total=12, page=page, rows=count))

    rows = _client(handler, page_size=10).fetch_station_rows("12")

    assert pages == [1, 2]
    assert len(rows) == 12


def test_an_empty_page_ends_the_walk_even_if_the_count_disagrees():
    """totalCount가 실제 행 수보다 크면 빈 페이지가 끝이다."""
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pageNo"])
        pages.append(page)
        items = [_row("ST-1", "01")] if page == 1 else []
        return httpx.Response(200, text=_body(items, total=9999, page=page))

    rows = _client(handler).fetch_station_rows("12")

    assert pages == [1, 2]
    assert len(rows) == 1


def test_never_walks_past_the_page_limit():
    """행이 계속 오는데 totalCount를 못 채우는 서버에도 영원히 매달리지 않는다."""
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pages.append(int(request.url.params["pageNo"]))
        return httpx.Response(200, text=_body([_row("ST-1", "01")], total=10**9, page=1))

    _client(handler).fetch_station_rows("12")

    assert len(pages) == MAX_PAGES


def test_status_endpoint_takes_a_period():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=_body([], total=0, page=1))

    _client(handler).fetch_status_rows("12", period=10)

    assert seen[0].url.path.endswith("/getChargerStatus")
    assert seen[0].url.params["period"] == "10"


def test_empty_result_is_an_empty_list_not_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=json.dumps({"items": "", "resultCode": "00",
                                                    "resultMsg": "NORMAL SERVICE.",
                                                    "totalCount": 0, "pageNo": 1, "numOfRows": 10}))

    assert _client(handler).fetch_station_rows("12") == []


def test_result_code_other_than_00_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=json.dumps(
                {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}
            ),
        )

    with pytest.raises(ChargerApiError) as exc:
        _client(handler).fetch_station_rows("12")

    assert "30" in str(exc.value)
    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in str(exc.value)


def test_service_key_never_leaks_into_the_error_message():
    """포털은 인증 오류 본문에 보낸 키를 그대로 되비춰 준다. 그게 예외 문구를
    타고 로그·에러 트래킹으로 새면 키가 공개된다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=json.dumps(
                {"resultCode": "30", "resultMsg": f"SERVICE KEY {KEY} IS NOT REGISTERED"}
            ),
        )

    with pytest.raises(ChargerApiError) as exc:
        _client(handler).fetch_station_rows("12")

    assert KEY not in str(exc.value)
    assert KEY not in repr(exc.value)


def test_service_key_never_leaks_from_a_transport_failure():
    # httpx 예외 문구에는 요청 URL(=쿼리의 serviceKey)이 실린다.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed to connect to {request.url}", request=request)

    with pytest.raises(ChargerApiError) as exc:
        _client(handler).fetch_station_rows("12")

    assert KEY not in str(exc.value)


def test_retries_a_server_error_and_then_succeeds():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, text=_body([_row("ST-1", "01")], total=1, page=1))

    rows = _client(handler).fetch_station_rows("12")

    assert attempts["n"] == 3
    assert len(rows) == 1


def test_gives_up_after_the_attempt_limit():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, text="Service Unavailable")

    with pytest.raises(ChargerApiError):
        _client(handler).fetch_station_rows("12")

    # 무한정 다시 부르지 않는다 — 실패한 호출도 하루 1,000건을 깎는다.
    assert attempts["n"] == 3


def test_does_not_retry_a_client_error():
    """4xx는 다시 불러도 같은 답이다. 재시도는 할당량만 태운다."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(404, text="Not Found")

    with pytest.raises(ChargerApiError):
        _client(handler).fetch_station_rows("12")

    assert attempts["n"] == 1


def test_retries_a_timeout():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, text=_body([], total=0, page=1))

    _client(handler).fetch_station_rows("12")

    assert attempts["n"] == 2


def test_non_json_body_raises_instead_of_crashing():
    """소문자 dataType이나 포털 점검 공지는 JSON이 아니라 XML/HTML로 온다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<OpenAPI_ServiceResponse><cmmMsgHeader/></OpenAPI_...>")

    with pytest.raises(ChargerApiError):
        _client(handler).fetch_station_rows("12")


def test_a_single_item_object_is_still_a_list():
    """행이 하나면 item이 리스트가 아니라 객체로 오는 포털 API가 흔하다."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=json.dumps(
                {
                    "items": {"item": _row("ST-1", "01")},
                    "resultCode": "00",
                    "resultMsg": "NORMAL SERVICE.",
                    "totalCount": 1,
                    "pageNo": 1,
                    "numOfRows": 10,
                }
            ),
        )

    rows = _client(handler).fetch_station_rows("12")

    assert rows == [_row("ST-1", "01")]
