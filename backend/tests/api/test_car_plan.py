from datetime import datetime

import pytest

from evcharge.api.car_plan_service import (
    compose_no_charge_speech,
    compose_plan_speech,
    spoken_clock,
    spoken_range,
)
from evcharge.api.routes import car
from evcharge.domain.pricing import KST

NOW = datetime(2026, 10, 7, 17, 0, tzinfo=KST)

# /api/recommend 명세 예시(test_recommend.SPEC_EXAMPLE)와 같은 조건을 차량 값으로.
ARRIVAL = {
    "soc_now": 30,
    "battery_capacity_wh": 70000,
    "soc_target": 60,
    "plug_in_at": "2026-10-07T18:00",
    "depart_at": "2026-10-08T08:00",
}


def kst(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(car, "now_kst", lambda: NOW)


def post(client, **overrides):
    body = {**ARRIVAL, **overrides}
    return client.post("/api/car/plan", json={k: v for k, v in body.items() if v is not None})


# ── 엔드포인트 ──────────────────────────────────────────────────────────


def test_plan_matches_recommend_for_the_same_conditions(client):
    car_body = post(client).json()
    recommend_body = client.post(
        "/api/recommend",
        json={
            "battery_kwh": 70,
            "soc_now": 30,
            "soc_target": 60,
            "charger_kw": 7,
            "earliest_start": "2026-10-07T18:00",
            "deadline": "2026-10-08T08:00",
        },
    ).json()

    assert car_body["needs_charging"] is True
    assert car_body["plan"] == recommend_body["best"]
    assert car_body["baseline_now"] == recommend_body["baseline_now"]
    assert car_body["savings_won"] == recommend_body["savings_won"]
    assert car_body["assumptions"] == recommend_body["assumptions"]
    assert car_body["unverified_tariff_items"] == recommend_body["unverified_tariff_items"]


def test_reservation_crosses_midnight(client):
    body = post(client).json()

    assert body["plan"]["start"] == "2026-10-07T22:00:00+09:00"
    assert body["reservation"] == {
        "start_at": "2026-10-07T22:00:00+09:00",
        "end_at": "2026-10-08T01:00:00+09:00",
        "start_hhmm": "22:00",
        "end_hhmm": "01:00",
    }


def test_speech_reads_the_computed_values(client):
    body = post(client).json()

    assert body["savings_won"] > 0
    assert body["speech"] == (
        "오늘 밤 10시부터 내일 새벽 1시까지 충전하면 가장 쌉니다. "
        f"도착하자마자 충전하는 것보다 약 {body['savings_won']:,}원 아낍니다. "
        "도착하면 차량 예약 충전을 밤 10시 시작, 새벽 1시 종료로 설정해 주세요."
    )


def test_reservation_end_is_rounded_up_to_the_minute(client):
    # 70kWh × 30.1% / 7kW = 3시간 0분 36초
    body = post(client, soc_target=60.1).json()

    assert body["plan"]["end"] == "2026-10-08T01:00:36+09:00"
    assert body["reservation"]["end_at"] == "2026-10-08T01:01:00+09:00"
    assert body["reservation"]["end_hhmm"] == "01:01"
    assert "새벽 1시 1분 종료" in body["speech"]


def test_battery_capacity_is_converted_from_wh(client):
    body = post(client, battery_capacity_wh=77400, soc_now=20, soc_target=80).json()

    assert body["plan"]["energy_kwh"] == pytest.approx(77.4 * 0.6, abs=0.001)


def test_defaults_target_80_and_7kw(client):
    body = post(client, soc_target=None).json()

    # 70kWh × (80 - 30)% = 35kWh, 7kW로 5시간
    assert body["plan"]["energy_kwh"] == pytest.approx(35.0)
    assert body["reservation"]["start_hhmm"] == "22:00"
    assert body["reservation"]["end_hhmm"] == "03:00"


def test_missing_plug_in_uses_server_now(client):
    body = post(client, plug_in_at=None).json()

    assert body["baseline_now"]["start"] == "2026-10-07T17:00:00+09:00"
    # 이미 꽂혀 있으니 "도착하면"이 아니라 "지금 바로"와 비교한다.
    assert "지금 바로 충전하는 것보다" in body["speech"]
    assert "도착하면" not in body["speech"]
    assert body["speech"].endswith(
        "차량 예약 충전을 밤 10시 시작, 새벽 1시 종료로 설정해 주세요."
    )


def test_server_now_with_seconds_never_starts_the_reservation_early(client, monkeypatch):
    monkeypatch.setattr(car, "now_kst", lambda: kst(2026, 10, 7, 22, 3, 27))
    body = post(client, plug_in_at=None).json()

    # 경부하에 이미 들어와 있으니 바로 시작이 가장 싸다. 시작이 22:03:27이다.
    assert body["plan"]["start"] == "2026-10-07T22:03:27+09:00"
    assert body["reservation"]["start_at"] == "2026-10-07T22:04:00+09:00"
    # 70kWh × 30% / 7kW = 3시간
    assert body["reservation"]["end_at"] == "2026-10-08T01:04:00+09:00"


def test_past_plug_in_is_pulled_up_to_now(client, monkeypatch):
    # 도착 예정 22:00이 이미 지난 22:10에 다시 계산한다.
    monkeypatch.setattr(car, "now_kst", lambda: kst(2026, 10, 7, 22, 10))
    body = post(client, plug_in_at="2026-10-07T22:00").json()

    assert body["baseline_now"]["start"] == "2026-10-07T22:10:00+09:00"
    assert body["plan"]["start"] == "2026-10-07T22:10:00+09:00"
    assert body["reservation"]["start_at"] == "2026-10-07T22:10:00+09:00"
    # 이미 꽂혀 있을 시각이니 "도착하면"이 아니라 "지금 바로"다.
    assert "도착하면" not in body["speech"]
    assert "밤 10시 10분 시작" in body["speech"]


def test_no_savings_says_there_is_no_difference(client):
    body = post(client, plug_in_at="2026-10-07T23:00", depart_at="2026-10-08T07:00").json()

    assert body["savings_won"] == 0
    assert "바로 충전해도 요금 차이가 없습니다." in body["speech"]
    assert "아낍니다" not in body["speech"]
    assert body["reservation"]["start_hhmm"] == "23:00"


@pytest.mark.parametrize("soc_target", [30, 25])
def test_target_at_or_below_now_needs_no_charging(client, soc_target):
    response = post(client, soc_target=soc_target)

    assert response.status_code == 200
    body = response.json()
    assert body["needs_charging"] is False
    assert body["plan"] is None
    assert body["baseline_now"] is None
    assert body["savings_won"] is None
    assert body["reservation"] is None
    assert body["assumptions"] == []
    assert "public_fast.base_price_per_kwh" in body["unverified_tariff_items"]
    assert body["speech"] == f"잔량 30%가 목표 {soc_target}% 이상이라 충전하지 않아도 됩니다."


def test_insufficient_time_is_the_existing_422(client):
    response = post(client, depart_at="2026-10-07T20:00")

    assert response.status_code == 422
    assert response.json()["detail"].startswith("시간이 부족해요.")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"depart_at": "2026-10-07T18:00"}, "depart_at은 plug_in_at보다 뒤여야 합니다."),
        ({"plug_in_at": None, "depart_at": "2026-10-07T16:00"}, "depart_at은 현재 시각보다"),
        ({"depart_at": "2026-10-22T18:00"}, "14일을 넘을 수 없습니다."),
        # 충전이 필요 없어도 시각 검사는 한다.
        ({"soc_target": 20, "depart_at": "2026-10-07T17:30"}, "depart_at은 plug_in_at보다"),
        # 이미 지난 출발 시각은 꽂는 시각이 더 이르더라도 422다.
        (
            {"plug_in_at": "2026-10-07T15:00", "depart_at": "2026-10-07T16:30"},
            "depart_at은 현재 시각보다 뒤여야 합니다.",
        ),
        ({"plug_in_at": "2026-10-07T15:00", "depart_at": "2026-10-07T17:00"}, "현재 시각보다"),
        ({"soc_target": 20, "depart_at": "2026-10-07T16:00"}, "현재 시각보다"),
    ],
)
def test_bad_time_window_is_a_validation_422(client, overrides, message):
    response = post(client, **overrides)

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["body", "depart_at"]
    assert message in error["msg"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"soc_now": 100},
        {"soc_now": -1},
        {"soc_target": 0},
        {"soc_target": 100.5},
        {"battery_capacity_wh": 0},
        {"battery_capacity_wh": 1_000_001},
        {"battery_capacity_wh": "Infinity"},
        {"charger_kw": 0},
        {"mode": "fast"},
        {"depart_at": None},
    ],
)
def test_out_of_range_input_is_422(client, overrides):
    response = post(client, **overrides)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


# ── 문장 (순수 함수) ────────────────────────────────────────────────────


def test_spoken_range_drops_repeated_day_and_period():
    assert spoken_range(kst(2026, 10, 8, 1), kst(2026, 10, 8, 5, 30), NOW) == (
        "내일 새벽 1시부터 5시 30분까지"
    )
    assert spoken_range(kst(2026, 10, 7, 22), kst(2026, 10, 8, 1), NOW) == (
        "오늘 밤 10시부터 내일 새벽 1시까지"
    )
    assert spoken_range(kst(2026, 10, 8, 4), kst(2026, 10, 8, 9, 15), NOW) == (
        "내일 새벽 4시부터 오전 9시 15분까지"
    )


def test_spoken_range_reads_midnight_as_the_previous_night():
    assert spoken_range(kst(2026, 10, 7, 21), kst(2026, 10, 8, 0), NOW) == (
        "오늘 밤 9시부터 12시까지"
    )


def test_spoken_range_reads_the_zero_hour_without_a_period():
    assert spoken_range(kst(2026, 10, 7, 22), kst(2026, 10, 8, 0, 29), NOW) == (
        "오늘 밤 10시부터 내일 0시 29분까지"
    )
    assert spoken_range(kst(2026, 10, 8, 0, 1), kst(2026, 10, 8, 3), NOW) == (
        "내일 0시 1분부터 새벽 3시까지"
    )
    assert spoken_range(kst(2026, 10, 8, 0, 1), kst(2026, 10, 8, 0, 29), NOW) == (
        "내일 0시 1분부터 0시 29분까지"
    )


def test_plan_speech_reads_a_zero_hour_end_in_the_reservation_sentence():
    speech = compose_plan_speech(
        window=(kst(2026, 10, 7, 22), kst(2026, 10, 8, 0, 29)),
        savings_won=0,
        reservable=True,
        arriving=False,
        now=NOW,
    )

    assert speech.endswith("차량 예약 충전을 밤 10시 시작, 0시 29분 종료로 설정해 주세요.")
    assert "12시 29분" not in speech


def test_spoken_range_uses_the_date_beyond_the_day_after_tomorrow():
    assert spoken_range(kst(2026, 10, 10, 11), kst(2026, 10, 10, 14), NOW) == (
        "10월 10일 오전 11시부터 오후 2시까지"
    )


@pytest.mark.parametrize(
    ("moment", "spoken"),
    [
        (kst(2026, 10, 8, 0, 1), "0시 1분"),
        (kst(2026, 10, 8, 0, 29), "0시 29분"),
        (kst(2026, 10, 8, 1), "새벽 1시"),
        (kst(2026, 10, 8, 5, 59), "새벽 5시 59분"),
        (kst(2026, 10, 8, 6), "오전 6시"),
        (kst(2026, 10, 8, 12), "낮 12시"),
        (kst(2026, 10, 8, 13, 5), "오후 1시 5분"),
        (kst(2026, 10, 8, 18), "저녁 6시"),
        (kst(2026, 10, 8, 21), "밤 9시"),
        (kst(2026, 10, 8, 0), "밤 12시"),
    ],
)
def test_spoken_clock(moment, spoken):
    assert spoken_clock(moment) == spoken


def test_plan_speech_with_savings_and_reservation():
    speech = compose_plan_speech(
        window=(kst(2026, 10, 8, 1), kst(2026, 10, 8, 5, 30)),
        savings_won=4100,
        reservable=True,
        arriving=True,
        now=NOW,
    )

    assert speech == (
        "내일 새벽 1시부터 5시 30분까지 충전하면 가장 쌉니다. "
        "도착하자마자 충전하는 것보다 약 4,100원 아낍니다. "
        "도착하면 차량 예약 충전을 새벽 1시 시작, 새벽 5시 30분 종료로 설정해 주세요."
    )


def test_plan_speech_without_savings():
    speech = compose_plan_speech(
        window=(kst(2026, 10, 7, 23), kst(2026, 10, 8, 2)),
        savings_won=0,
        reservable=True,
        arriving=False,
        now=NOW,
    )

    assert "바로 충전해도 요금 차이가 없습니다." in speech
    assert "원" not in speech
    assert speech.endswith("차량 예약 충전을 밤 11시 시작, 새벽 2시 종료로 설정해 주세요.")


def test_plan_speech_when_one_reservation_cannot_hold_it():
    speech = compose_plan_speech(
        window=(kst(2026, 10, 7, 22), kst(2026, 10, 9, 1)),
        savings_won=0,
        reservable=False,
        arriving=False,
        now=NOW,
    )

    assert "예약 충전을" not in speech
    assert speech.endswith("차량 예약 충전 한 번으로는 설정할 수 없습니다.")


def test_plan_speech_when_the_window_rounds_to_nothing():
    speech = compose_plan_speech(
        window=(kst(2026, 10, 7, 18, 1), kst(2026, 10, 7, 18, 0)),
        savings_won=0,
        reservable=False,
        arriving=False,
        now=NOW,
    )

    assert speech == (
        "충전할 양이 아주 적어 차량 예약 충전으로 설정할 수 없습니다. 출발 전에 바로 충전해 주세요."
    )


def test_tight_window_with_seconds_keeps_the_reservation_before_departure(client, monkeypatch):
    monkeypatch.setattr(car, "now_kst", lambda: kst(2026, 10, 7, 18, 0, 30))
    # 70kWh × 30% / 7kW = 3시간. 지금부터 출발까지 꼭 3시간이다.
    body = post(client, plug_in_at=None, depart_at="2026-10-07T21:00:30").json()

    assert body["reservation"]["start_at"] == "2026-10-07T18:01:00+09:00"
    assert body["reservation"]["end_at"] == "2026-10-07T21:00:00+09:00"
    assert "저녁 6시 1분 시작, 밤 9시 종료" in body["speech"]


def test_plan_speech_has_no_markdown_or_symbols():
    speech = compose_plan_speech(
        window=(kst(2026, 10, 8, 1), kst(2026, 10, 8, 5, 30)),
        savings_won=12345,
        reservable=True,
        arriving=True,
        now=NOW,
    )

    assert not set(speech) & set("*#`_[]()<>|~")
    assert "12,345원" in speech


@pytest.mark.parametrize(
    ("soc_now", "soc_target", "spoken"),
    [(85, 80, "잔량 85%가 목표 80%"), (80.0, 80, "잔량 80%가 목표 80%"), (82.46, 80, "잔량 82.5%")],
)
def test_no_charge_speech(soc_now, soc_target, spoken):
    speech = compose_no_charge_speech(soc_now, soc_target)

    assert speech.startswith(spoken)
    assert speech.endswith("충전하지 않아도 됩니다.")
