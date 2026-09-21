import pytest

SPEC_EXAMPLE = {
    "battery_kwh": 70,
    "soc_now": 30,
    "soc_target": 60,
    "charger_kw": 7,
    "earliest_start": "2026-10-07T18:00",
    "deadline": "2026-10-08T08:00",
}


def post(client, **overrides):
    return client.post("/api/recommend", json={**SPEC_EXAMPLE, **overrides})


def test_spec_example_reproduces(client):
    """API 명세서 2-2의 예시 요청을 그대로 보낸다."""
    response = post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["best"]["energy_kwh"] == pytest.approx(21.0)
    assert body["candidates_checked"] == 45
    assert body["best"]["start"] == "2026-10-07T22:00:00+09:00"
    assert body["best"]["end"] == "2026-10-08T01:00:00+09:00"
    assert body["baseline_now"]["start"] == "2026-10-07T18:00:00+09:00"
    assert body["savings_won"] > 0
    assert (
        body["savings_won"]
        == body["baseline_now"]["cost_won"] - body["best"]["cost_won"]
    )
    assert len(body["assumptions"]) >= 3
    assert "adders.climate_env_per_kwh" in body["unverified_tariff_items"]


def test_naive_input_is_read_as_kst(client):
    body = post(client).json()
    assert body["baseline_now"]["start"].endswith("+09:00")


def test_explicit_timezone_is_respected(client):
    body = post(
        client,
        earliest_start="2026-10-07T09:00:00+00:00",  # = KST 18:00
        deadline="2026-10-07T23:00:00+00:00",
    ).json()

    assert body["baseline_now"]["start"] == "2026-10-07T18:00:00+09:00"


def test_business_error_returns_a_detail_string(client):
    response = post(client, deadline="2026-10-07T20:00")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert "시간이 부족합니다" in response.json()["detail"]


def test_validation_error_returns_a_detail_array(client):
    response = post(client, soc_target=20)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_target_must_exceed_current_soc(client):
    response = post(client, soc_now=60, soc_target=60)
    assert response.status_code == 422


def test_deadline_must_follow_earliest_start(client):
    response = post(client, deadline="2026-10-07T17:00")
    assert response.status_code == 422


def test_mode_defaults_to_self_low(client):
    assert post(client).status_code == 200
    assert post(client, mode="self_low").json() == post(client).json()


def test_battery_and_charger_are_required_without_a_vehicle(client):
    payload = dict(SPEC_EXAMPLE)
    del payload["battery_kwh"]
    response = client.post("/api/recommend", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_vehicle_id_requires_login(client):
    response = post(client, vehicle_id="v_01")
    assert response.status_code == 401
