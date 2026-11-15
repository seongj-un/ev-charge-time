"""JSON의 NaN, Infinity는 500이 아니라 422다 (공통 RequestValidationError 핸들러)."""

from __future__ import annotations

import json

import pytest

HEADERS = {"content-type": "application/json"}
CASES = [
    (
        "/api/car/chargers/along-route",
        '{"origin": {"lat": NaN, "lng": 126.8}, "destination": {"lat": 35.5, "lng": 126.8},'
        ' "soc_now": 60}',
        ["body", "origin", "lat"],
        "NaN",
    ),
    (
        "/api/car/chargers/along-route",
        '{"origin": {"lat": 35, "lng": 126.8}, "destination": {"lat": 35.5, "lng": 126.8},'
        ' "soc_now": 60, "remain_distance_m": -Infinity}',
        ["body", "remain_distance_m"],
        "-Infinity",
    ),
    (
        "/api/car/plan",
        '{"soc_now": NaN, "battery_capacity_wh": 77400, "depart_at": "2026-11-17T08:00"}',
        ["body", "soc_now"],
        "NaN",
    ),
    (
        "/api/car/leak-check",
        '{"soc_now": 32, "battery_capacity_wh": Infinity}',
        ["body", "battery_capacity_wh"],
        "Infinity",
    ),
    (
        "/api/recommend",
        '{"battery_kwh": NaN, "soc_now": 32, "soc_target": 80, "charger_kw": 7,'
        ' "earliest_start": "2026-11-16T18:00", "deadline": "2026-11-17T08:00"}',
        ["body", "battery_kwh"],
        "NaN",
    ),
]


@pytest.mark.parametrize(("url", "body", "loc", "shown"), CASES)
def test_non_finite_numbers_are_422_with_the_input_as_text(client, url, body, loc, shown):
    response = client.post(url, content=body, headers=HEADERS)

    assert response.status_code == 422
    errors = response.json()["detail"]
    error = next(e for e in errors if e["loc"] == loc)
    assert error["input"] == shown


def test_other_validation_errors_keep_the_default_shape(client):
    response = client.post(
        "/api/car/chargers/along-route",
        content=json.dumps({"origin": {"lat": 35, "lng": 126.8}, "soc_now": 60}),
        headers=HEADERS,
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "destination"],
                "msg": "Field required",
                "input": {"origin": {"lat": 35, "lng": 126.8}, "soc_now": 60},
            }
        ]
    }
