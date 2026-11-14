"""요청 시각의 연도 범위. datetime 범위를 넘는 계산이 본문 없는 500이 되지 않게 422로 막는다."""

from __future__ import annotations

from datetime import datetime

import pytest

from evcharge.api.routes import car
from evcharge.api.schemas import MAX_REQUEST_YEAR, MIN_REQUEST_YEAR, to_kst
from evcharge.domain.pricing import KST

OUT_OF_RANGE = [
    # KST로 옮기면 9999년이 되는 값: 서비스가 요청 모델을 다시 만들 때 500이 나던 경로
    "9998-12-31T23:59:00-12:00",
    "9999-12-31T23:59",
    "9999-12-31T23:59:00+00:00",
    "9999-01-01T00:00:00+09:00",
    "0001-01-01T00:00:00+09:00",
    "1969-12-31T23:59:00+09:00",
    # KST로 옮기면 1969년
    "1970-01-01T00:00:00+14:00",
]
# 범위 끝이지만 계산이 넘치지 않아야 하는 값 (422든 200이든 500만 아니면 된다)
EDGES = [
    "9998-12-31T14:59:00+00:00",
    "1970-01-01T09:00:00+09:00",
    "1970-01-01T00:00:00Z",
]
BASE_RECOMMEND = {
    "battery_kwh": 77.4,
    "soc_now": 32,
    "soc_target": 80,
    "charger_kw": 7,
    "mode": "self_low",
    "earliest_start": "2026-11-16T18:00",
    "deadline": "2026-11-17T08:00",
}
CAR = {"soc_now": 32, "battery_capacity_wh": 77400}


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch):
    monkeypatch.setattr(car, "now_kst", lambda: datetime(2026, 11, 16, 18, tzinfo=KST))


def _requests(moment: str):
    return [
        ("/api/car/plan", {**CAR, "depart_at": moment}, "depart_at"),
        (
            "/api/car/plan",
            {**CAR, "plug_in_at": moment, "depart_at": "2026-11-17T08:00"},
            "plug_in_at",
        ),
        ("/api/car/leak-check", {**CAR, "depart_at": moment}, "depart_at"),
        ("/api/recommend", {**BASE_RECOMMEND, "deadline": moment}, "deadline"),
        ("/api/recommend", {**BASE_RECOMMEND, "earliest_start": moment}, "earliest_start"),
    ]


@pytest.mark.parametrize("moment", OUT_OF_RANGE)
def test_out_of_range_years_are_422_on_the_field(client, moment):
    for url, body, field in _requests(moment):
        response = client.post(url, json=body)

        assert response.status_code == 422, (url, field, response.text)
        error = response.json()["detail"][0]
        assert error["loc"] == ["body", field]
        assert "1970년부터 9998년 사이" in error["msg"]


@pytest.mark.parametrize("moment", EDGES)
def test_edge_years_never_overflow(client, moment):
    for url, body, _field in _requests(moment):
        response = client.post(url, json=body)

        assert response.status_code in (200, 422), (url, response.text)
        assert response.headers["content-type"].startswith("application/json")


def test_normal_requests_are_unchanged(client):
    plan = {**CAR, "depart_at": "2026-11-17T08:00"}
    assert client.post("/api/car/plan", json=plan).status_code == 200
    assert client.post("/api/recommend", json=BASE_RECOMMEND).status_code == 200


def test_to_kst_reads_naive_as_kst_and_converts_offsets():
    assert to_kst(datetime(2026, 11, 16, 18)) == datetime(2026, 11, 16, 18, tzinfo=KST)
    utc = datetime.fromisoformat("2026-11-16T09:00:00+00:00")
    assert to_kst(utc).isoformat() == "2026-11-16T18:00:00+09:00"
    assert to_kst(None) is None
    assert (MIN_REQUEST_YEAR, MAX_REQUEST_YEAR) == (1970, 9998)


@pytest.mark.parametrize("moment", OUT_OF_RANGE)
def test_voice_arrival_at_out_of_range_is_422(client, moment):
    token = client.post("/api/car/devices").json()["device_token"]

    response = client.post(
        "/api/car/voice",
        json={"text": "8시", "context": {**CAR, "arrival_at": moment}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "context", "arrival_at"]
