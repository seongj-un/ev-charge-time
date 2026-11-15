"""목표 충전량 추천 POST /api/car/charge-target (BE-11)."""

from __future__ import annotations

import pytest

URL = "/api/car/charge-target"
# 전비 5km/kWh x 40kWh = 100%로 200km. 1km = 0.5%
BASE = {"battery_capacity_wh": 40_000, "efficiency_km_per_kwh": 5}


def post(client, **body):
    return client.post(URL, json={**BASE, **body})


@pytest.mark.parametrize(
    "body",
    [
        {"battery_capacity_wh": 40_000},
        {"battery_capacity_wh": 40_000, "next_trip_km": 150},
        {"battery_capacity_wh": 40_000, "efficiency_km_per_kwh": 5},
    ],
)
def test_without_distance_or_efficiency_it_is_the_daily_target(client, body):
    response = client.post(URL, json=body)

    assert response.status_code == 200
    out = response.json()
    assert (out["soc_target"], out["reason"], out["needed_soc"]) == (80, "unknown", None)
    assert out["needs_charge_on_route"] is False
    assert "충분" not in out["speech"]
    assert "평소 기준 80%" in out["assumptions"][0]


def test_unknown_distance_asks_for_it_instead_of_saying_enough(client):
    no_distance = client.post(URL, json={"battery_capacity_wh": 40_000}).json()["speech"]
    no_efficiency = client.post(
        URL, json={"battery_capacity_wh": 40_000, "next_trip_km": 330}
    ).json()["speech"]
    parked_full = client.post(URL, json={"battery_capacity_wh": 40_000, "soc_now": 85}).json()

    assert no_distance == (
        "다음 이동 거리를 몰라서 평소처럼 80%를 권해요. 멀리 가시면 거리를 말씀해 주세요."
    )
    assert no_efficiency == "전비를 몰라서 평소처럼 80%를 권해요."
    # 잔량 문장은 질문 앞에 둔다(질문으로 끝나야 운전자가 바로 답한다).
    assert parked_full["speech"] == (
        "다음 이동 거리를 몰라서 평소처럼 80%를 권해요. 지금 85%라 더 채우지 않아도 돼요. "
        "멀리 가시면 거리를 말씀해 주세요."
    )


def test_assumption_names_what_is_missing(client):
    both = client.post(URL, json={"battery_capacity_wh": 40_000}).json()
    distance = post(client).json()

    assert both["assumptions"] == ["다음 이동 거리와 전비를 몰라 평소 기준 80%로 정했어요."]
    assert distance["assumptions"] == ["다음 이동 거리를 몰라 평소 기준 80%로 정했어요."]


@pytest.mark.parametrize(
    ("km", "target", "reason", "needed"),
    [
        (10, 80, "daily", 5.0),
        (120, 80, "daily", 60.0),  # 60 + 20 = 80: 평소 목표 그대로
        (122, 85, "long_trip", 61.0),  # 81 → 5% 올림 85
        (150, 95, "long_trip", 75.0),  # 정확히 95: 한 칸 위로 가지 않는다
        (160, 100, "long_trip", 80.0),  # 정확히 100: 아직 모자라지 않다
        (161, 100, "insufficient", 80.5),  # 100.5
        (210, 100, "insufficient", 105.0),  # 필요 잔량만으로 100 초과
    ],
)
def test_target_boundaries(client, km, target, reason, needed):
    out = post(client, next_trip_km=km).json()

    assert (out["soc_target"], out["reason"], out["needed_soc"]) == (target, reason, needed)
    assert out["needs_charge_on_route"] is (reason == "insufficient")


@pytest.mark.parametrize(
    ("km", "efficiency", "capacity_wh", "needed"),
    [
        # float로 나누면 70.00000000000001, 65.00000000000001이 되는 입력이다.
        (128.8, 4.6, 40_000, 70.0),
        (137.8, 5.3, 40_000, 65.0),
        (144.3, 3.7, 60_000, 65.0),
    ],
)
def test_exact_multiple_with_decimal_inputs_does_not_round_up_a_step(
    client, km, efficiency, capacity_wh, needed
):
    out = client.post(
        URL,
        json={
            "battery_capacity_wh": capacity_wh,
            "efficiency_km_per_kwh": efficiency,
            "next_trip_km": km,
        },
    ).json()

    assert (out["soc_target"], out["needed_soc"]) == (int(needed) + 20, needed)


def test_long_trip_speech(client):
    out = client.post(
        URL,
        json={"battery_capacity_wh": 61_340, "efficiency_km_per_kwh": 5, "next_trip_km": 230},
    ).json()

    assert out["speech"] == "230킬로미터를 가시려면 95%까지 채우세요."
    assert out["assumptions"] == [
        "충전 후 평균 전비 5km/kWh와 배터리 용량 61.34kWh로 계산했어요. 도착 여유 20%p를 더했어요."
    ]


def test_insufficient_speech_tells_reserve_from_running_out(client):
    short_of_reserve = post(client, next_trip_km=161).json()["speech"]
    runs_out = post(client, next_trip_km=210).json()["speech"]

    assert short_of_reserve == (
        "100%로 채워도 도착할 때 여유가 부족해요. 가는 길에 급속충전을 한 번 하세요."
    )
    assert runs_out == (
        "100%로 채워도 도착하기 전에 배터리가 모자라요. 가는 길에 급속충전을 하세요."
    )


@pytest.mark.parametrize(
    ("soc_now", "suffix"),
    [
        (85, " 지금 85%라 더 채우지 않아도 돼요."),
        (80, " 지금 80%라 더 채우지 않아도 돼요."),
        (79.5, ""),
    ],
)
def test_soc_now_at_or_above_the_target_says_no_charge_needed(client, soc_now, suffix):
    out = post(client, next_trip_km=100, soc_now=soc_now).json()  # 50 + 20 → 평소 80

    assert out["speech"] == "평소처럼 80%까지만 채우면 충분해요." + suffix
    assert out["soc_target"] == 80


def test_targets_come_from_settings(client, monkeypatch):
    monkeypatch.setenv("CAR_TARGET_DAILY", "90")
    monkeypatch.setenv("CAR_TARGET_RESERVE", "10")

    daily = post(client, next_trip_km=100).json()  # 50 + 10 → 평소 90
    trip = post(client, next_trip_km=170).json()  # 85 + 10 = 95

    assert (daily["soc_target"], daily["speech"]) == (90, "평소처럼 90%까지만 채우면 충분해요.")
    assert (trip["soc_target"], trip["reason"]) == (95, "long_trip")


@pytest.mark.parametrize(
    "body",
    [
        {"battery_capacity_wh": 500},
        {**BASE, "efficiency_km_per_kwh": 0},
        {**BASE, "efficiency_km_per_kwh": 21},
        {**BASE, "next_trip_km": 0},
        {**BASE, "next_trip_km": 3001},
        {**BASE, "soc_now": 101},
        {"efficiency_km_per_kwh": 5},
    ],
)
def test_out_of_range_input_is_422(client, body):
    assert client.post(URL, json=body).status_code == 422


def test_nan_is_422(client):
    response = client.post(
        URL,
        content='{"battery_capacity_wh": 40000, "next_trip_km": NaN}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422


def test_device_token_changes_nothing(client):
    plain = post(client, next_trip_km=150).json()
    with_token = client.post(
        URL, json={**BASE, "next_trip_km": 150}, headers={"Authorization": "Bearer nope"}
    ).json()

    assert plain == with_token


def test_needing_exactly_100_percent_runs_out(client):
    # 77.4kWh x 5km/kWh = 387km. 도착 추정 0%
    out = client.post(
        URL,
        json={"battery_capacity_wh": 77_400, "efficiency_km_per_kwh": 5, "next_trip_km": 387},
    ).json()

    assert (out["soc_target"], out["reason"], out["needed_soc"]) == (100, "insufficient", 100.0)
    assert out["speech"] == (
        "100%로 채워도 도착하기 전에 배터리가 모자라요. 가는 길에 급속충전을 하세요."
    )


def test_needing_exactly_100_percent_runs_out_even_without_a_reserve(client, monkeypatch):
    monkeypatch.setenv("CAR_TARGET_RESERVE", "0")

    out = post(client, next_trip_km=200).json()  # 정확히 100%

    assert (out["reason"], out["needs_charge_on_route"]) == ("insufficient", True)


@pytest.mark.parametrize("efficiency", [5e-324, 1e-300, 0.49])
def test_tiny_efficiency_is_422_not_500(client, efficiency):
    # gt=0만 있을 때는 5e-324 x 3,000km가 OverflowError(500)를 냈다.
    response = post(client, efficiency_km_per_kwh=efficiency, next_trip_km=3000)

    assert response.status_code == 422


def test_lowest_efficiency_still_computes(client):
    out = post(client, efficiency_km_per_kwh=0.5, next_trip_km=3000).json()

    assert (out["reason"], out["needed_soc"]) == ("insufficient", 15000.0)


@pytest.mark.parametrize(
    ("url", "body"),
    [
        (
            "/api/car/chargers/along-route",
            {
                "origin": {"lat": 35.0, "lng": 126.8},
                "destination": {"lat": 35.5, "lng": 126.8},
                "soc_now": 60,
                "battery_capacity_wh": 77_400,
                "efficiency_km_per_kwh": 5e-324,
            },
        ),
        (
            "/api/car/voice",
            {
                "text": "몇 퍼센트까지?",
                "context": {
                    "soc_now": 60,
                    "battery_capacity_wh": 77_400,
                    "efficiency_km_per_kwh": 5e-324,
                },
            },
        ),
    ],
)
def test_tiny_efficiency_is_422_on_the_other_endpoints(client, url, body):
    assert client.post(url, json=body).status_code == 422
