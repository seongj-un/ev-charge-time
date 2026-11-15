"""와트잇 BE-9 시동 ON 브리핑 (``POST /api/car/briefing``)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from evcharge.api.routes import car
from evcharge.domain.pricing import KST
from evcharge.infra.models import CarDeparture, CarDevice, CarSaving
from evcharge.infra.security import hash_token

URL = "/api/car/briefing"
BODY = {"soc_now": 32, "battery_capacity_wh": 77400}
# 2026-11-16(월) 18:00, 겨울 평일 최대부하(16~19시)
MONDAY_EVENING = datetime(2026, 11, 16, 18, 0, tzinfo=KST)

EVENING_SPEECH = (
    "지금은 요금이 비싼 시간이고, 저녁 7시부터 싸져요. 배터리가 32%라 오늘 밤 충전하세요. "
    "내일 오전 8시 출발 기준으로 밤 10시부터 새벽 3시 19분까지 "
    "예약하면 약 1,995원 아껴요."
)
DEFAULT_ASSUMPTION = "출발 시각 미입력: 11월 17일 오전 8시(KST) 출발로 가정"


def at(moment: datetime):
    return lambda: moment


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(car, "now_kst", at(MONDAY_EVENING))


def register(client) -> dict[str, str]:
    body = client.post("/api/car/devices").json()
    return {"Authorization": f"Bearer {body['device_token']}"}


def brief(client, headers=None, **body):
    return client.post(URL, json={**BODY, **body}, headers=headers or {})


def savings(db_session) -> list[CarSaving]:
    return list(db_session.scalars(select(CarSaving)))


def sentences(speech: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.?!])\s+", speech.strip()) if part]


# ── price ───────────────────────────────────────────────────────────────


def test_weekday_peak_evening(client, db_session):
    response = brief(client)

    assert response.status_code == 200
    body = response.json()
    assert body["speech"] == EVENING_SPEECH
    assert body["price"] == {
        "band": "peak",
        "band_label": "최대부하",
        "price_per_kwh": 260.9,
        "discounted": False,
        "next_cheaper_at": "2026-11-16T19:00:00+09:00",
        "next_cheaper_price_per_kwh": 190.4,
        "discount_window": None,
    }
    assert body["actions"] == [
        {"type": "set_reservation", "start_hhmm": "22:00", "end_hhmm": "03:19"}
    ]
    assert body["tonight"]["depart_basis"] == "default"
    assert body["tonight"]["savings_won"] == 1995
    assert DEFAULT_ASSUMPTION in body["assumptions"]
    assert body["savings"] is None
    assert body["saving_id"] is None
    assert savings(db_session) == []


def test_numbers_match_the_existing_services(client):
    """새 계산 없음: 단가는 /api/timeline, 예약·금액은 /api/car/plan과 같다."""
    body = brief(client).json()
    hours = client.get("/api/timeline", params={"day": "2026-11-16"}).json()["hours"]
    plan = client.post(
        "/api/car/plan",
        json={**BODY, "plug_in_at": "2026-11-16T18:00", "depart_at": "2026-11-17T08:00"},
    ).json()

    assert body["price"]["price_per_kwh"] == hours[18]["price_per_kwh"]
    assert body["price"]["next_cheaper_price_per_kwh"] == hours[19]["price_per_kwh"]
    assert body["tonight"]["reservation"] == plan["reservation"]
    assert body["tonight"]["savings_won"] == plan["savings_won"]


def test_weekday_light_night(client, monkeypatch):
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 11, 16, 23, 0, tzinfo=KST)))

    body = brief(client).json()

    assert body["price"]["band_label"] == "경부하"
    assert body["price"]["next_cheaper_at"] is None
    assert sentences(body["speech"])[0] == "지금은 요금이 싼 시간이에요."
    # 이미 싼 시간이라 지금 꽂아도 같은 값: 아끼는 금액 없이 예약만 안내한다
    assert sentences(body["speech"])[-1] == (
        "내일 오전 8시 출발 기준으로 밤 11시부터 새벽 4시 19분까지 예약하세요."
    )


def test_weekend_discount_season(client, monkeypatch):
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 5, 16, 12, 0, tzinfo=KST)))  # 토

    body = brief(client, soc_now=60).json()

    assert body["price"]["discounted"] is True
    assert body["price"]["discount_window"] == {
        "start_at": "2026-05-16T11:00:00+09:00",
        "end_at": "2026-05-16T14:00:00+09:00",
    }
    assert body["speech"] == (
        "지금은 주말 할인 시간이라 요금이 싸요. 배터리가 60%라 오늘 밤은 충전 안 해도 돼요."
    )


def test_weekend_morning_points_at_the_discount(client, monkeypatch):
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 5, 16, 9, 0, tzinfo=KST)))

    body = brief(client).json()

    assert body["price"]["next_cheaper_at"] == "2026-05-16T11:00:00+09:00"
    assert sentences(body["speech"])[0] == "지금은 요금이 중간인 시간이고, 오전 11시부터 싸져요."
    # "오늘 밤" 예약이다. 낮 할인 구간을 고르지 않는다(저녁 6시 이후 꽂는다고 가정).
    assert body["actions"][0]["start_hhmm"] == "22:00"
    assert "충전기는 오늘 저녁 6시 이후에 꽂는다고 가정" in body["assumptions"]


def test_holiday(client, monkeypatch):
    # 2026-10-09(금) 한글날: 하루 종일 경부하, 낮에는 공휴일 할인
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 10, 9, 12, 0, tzinfo=KST)))
    noon = brief(client, soc_now=60).json()
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 10, 9, 16, 0, tzinfo=KST)))
    afternoon = brief(client, soc_now=60).json()

    assert sentences(noon["speech"])[0] == "지금은 공휴일 할인 시간이라 요금이 싸요."
    assert afternoon["price"]["band_label"] == "경부하"
    assert sentences(afternoon["speech"])[0] == "지금은 요금이 싼 시간이에요."


def test_public_fast_mode_is_422(client):
    assert brief(client, mode="public_fast").status_code == 422


def test_self_high_mode_uses_its_own_prices(client):
    low = brief(client).json()
    high = brief(client, mode="self_high").json()

    assert high["price"]["price_per_kwh"] != low["price"]["price_per_kwh"]


# ── tonight ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("soc", "needs"), [(49.9, True), (50, False), (100, False), (0, True)])
def test_low_soc_boundary(client, soc, needs):
    body = brief(client, soc_now=soc).json()

    assert body["tonight"]["needs_charging"] is needs
    assert bool(body["actions"]) is needs
    if not needs:
        assert sentences(body["speech"])[1] == f"배터리가 {soc:g}%라 오늘 밤은 충전 안 해도 돼요."


def test_low_soc_is_a_setting(client, monkeypatch):
    monkeypatch.setenv("CAR_BRIEFING_LOW_SOC", "60")

    body = brief(client, soc_now=55).json()

    assert body["tonight"]["needs_charging"] is True
    assert body["tonight"]["low_soc"] == 60


def test_morning_ignition_plans_for_tonight_from_the_evening(client, monkeypatch):
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 11, 16, 7, 30, tzinfo=KST)))

    body = brief(client).json()

    assert body["tonight"]["depart_at"] == "2026-11-17T08:00:00+09:00"
    assert body["actions"] == [
        {"type": "set_reservation", "start_hhmm": "22:00", "end_hhmm": "03:19"}
    ]
    # 아끼는 금액은 "저녁 6시에 꽂자마자 충전"과 비교한 값(저녁 브리핑과 같다)
    assert body["tonight"]["savings_won"] == 1995


def test_after_midnight_tonight_is_this_night(client, monkeypatch):
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 11, 17, 2, 0, tzinfo=KST)))

    body = brief(client).json()

    assert body["tonight"]["depart_at"] == "2026-11-17T08:00:00+09:00"
    assert sentences(body["speech"])[-1].startswith("오늘 오전 8시 출발 기준으로 새벽 2시부터")


def test_no_time_left_asks_to_charge_on_arrival(client, monkeypatch):
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 11, 17, 3, 50, tzinfo=KST)))

    response = brief(client, soc_now=10)

    assert response.status_code == 200
    assert sentences(response.json()["speech"])[-1] == (
        "출발 전까지 채우려면 도착하자마자 충전해 주세요."
    )
    assert response.json()["actions"] == []


# ── 기기 토큰 ─────────────────────────────────────────────────────────────


def test_wrong_token_changes_nothing(client, db_session):
    plain = brief(client).json()

    response = brief(client, {"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 200
    assert response.json() == plain
    assert savings(db_session) == []


def test_token_adds_one_briefing_record_and_nothing_else(client, db_session):
    plain = brief(client).json()

    body = brief(client, register(client)).json()

    assert {**body, "saving_id": None} == plain
    assert [(s.id, s.source, s.cause, s.savings_won) for s in savings(db_session)] == [
        (body["saving_id"], "briefing", "time", 1995)
    ]


def test_repeated_briefings_keep_one_record(client, db_session):
    headers = register(client)

    ids = {brief(client, headers).json()["saving_id"] for _ in range(3)}
    other = brief(client, headers, soc_now=20).json()["saving_id"]

    assert len(ids) == 1
    assert other not in ids
    # 다른 계획이면 새 기록이고, 브리핑 대기 기록은 기기당 하나라 이전 것은 지워진다
    assert [s.id for s in savings(db_session)] == [other]


def test_no_record_without_savings(client, db_session, monkeypatch):
    monkeypatch.setattr(car, "now_kst", at(datetime(2026, 11, 16, 23, 0, tzinfo=KST)))

    body = brief(client, register(client)).json()

    assert body["saving_id"] is None
    assert savings(db_session) == []


def seed_departures(client, headers, minutes: list[int]) -> None:
    """11월 9~13일(월~금) 07:00 + minutes 출발 기록."""
    for day, minute in zip((9, 10, 11, 12, 13), minutes, strict=False):
        moment = datetime(2026, 11, day, 7, 0, tzinfo=KST) + timedelta(minutes=minute)
        response = client.post(
            "/api/car/departures", json={"departed_at": moment.isoformat()}, headers=headers
        )
        assert response.status_code == 201


def test_high_usual_departure_replaces_8am(client):
    headers = register(client)
    seed_departures(client, headers, [0, 2, -3, 5, 0])

    body = brief(client, headers).json()

    assert body["tonight"]["depart_at"] == "2026-11-17T07:00:00+09:00"
    assert body["tonight"]["depart_basis"] == "usual"
    assert sentences(body["speech"])[-1].startswith("평소처럼 내일 오전 7시 출발 기준으로 ")
    assert (
        "출발 시각 미입력: 평소 출발 시각(5건 기준)으로 11월 17일 오전 7시(KST) 출발로 가정"
        in body["assumptions"]
    )


def test_low_usual_departure_keeps_8am(client):
    headers = register(client)
    seed_departures(client, headers, [0, 2, -3])

    body = brief(client, headers).json()

    assert body["tonight"]["depart_basis"] == "default"
    assert DEFAULT_ASSUMPTION in body["assumptions"]


def confirm_saving(client, headers, db_session, won: int) -> None:
    device = db_session.scalar(
        select(CarDevice).where(
            CarDevice.token_hash == hash_token(headers["Authorization"].split()[1])
        )
    )
    saving_id = str(uuid.uuid4())
    db_session.execute(
        text(
            "INSERT INTO car_savings (id, device_id, cause, savings_won, energy_kwh, source, "
            "confirmed_at) VALUES (:id, :device, 'time', :won, 20, 'plan', :at)"
        ),
        {"id": saving_id, "device": device.id, "won": won, "at": MONDAY_EVENING},
    )


def test_savings_sentence_when_the_month_has_savings(client, db_session):
    headers = register(client)
    confirm_saving(client, headers, db_session, 4200)

    body = brief(client, headers, soc_now=70).json()

    assert body["savings"] == {
        "month": "2026-11",
        "month_won": 4200,
        "year": 2026,
        "year_won": 4200,
    }
    assert sentences(body["speech"]) == [
        "지금은 요금이 비싼 시간이고, 저녁 7시부터 싸져요.",
        "배터리가 70%라 오늘 밤은 충전 안 해도 돼요.",
        "이번 달 와트잇으로 약 4,200원, 올해 약 4,200원 아꼈어요.",
    ]


def test_tonight_wins_over_savings_in_the_three_sentences(client, db_session):
    headers = register(client)
    confirm_saving(client, headers, db_session, 4200)

    body = brief(client, headers).json()

    assert body["savings"]["month_won"] == 4200  # 항목은 있고 문장만 빠진다
    assert body["speech"] == EVENING_SPEECH


def test_no_savings_sentence_without_this_months_savings(client, db_session):
    headers = register(client)

    body = brief(client, headers, soc_now=70).json()

    assert body["savings"] is None
    assert len(sentences(body["speech"])) == 2


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 11, 16, 7, 30, tzinfo=KST),
        datetime(2026, 11, 16, 18, 0, tzinfo=KST),
        datetime(2026, 11, 17, 2, 0, tzinfo=KST),
        datetime(2026, 5, 16, 9, 0, tzinfo=KST),
        datetime(2026, 10, 9, 12, 0, tzinfo=KST),
    ],
)
@pytest.mark.parametrize("soc", [5, 32, 49.9, 50, 90])
def test_never_more_than_three_sentences(client, db_session, monkeypatch, moment, soc):
    headers = register(client)
    seed_departures(client, headers, [0, 2, -3, 5, 0])
    confirm_saving(client, headers, db_session, 4200)
    monkeypatch.setattr(car, "now_kst", at(moment))

    speech = brief(client, headers, soc_now=soc).json()["speech"]

    assert 2 <= len(sentences(speech)) <= 3
    assert len(speech) <= MAX_SPEECH_CHARS


# 명세는 "약 120자". 8만여 조합(날짜 7개 × 30분 간격 × 잔량 6개 × 충전기 3.3~22kW × 요금제 2개
# × 평소 출발 5가지, 절약 합계 있음)을 돌린 실측 최대가 122자다. 아래 테스트가 그 조합을 담는다.
MAX_SPEECH_CHARS = 122


@pytest.mark.parametrize("moment", [(2026, 11, 16, 15, 30), (2026, 11, 16, 19, 0)])
@pytest.mark.parametrize(("soc", "kw"), [(12.3, 7.0), (5.5, 7.0), (40.5, 3.3), (49.9, 3.3)])
def test_longest_speech_found_in_the_grid(client, db_session, monkeypatch, moment, soc, kw):
    headers = register(client)
    seed_departures(client, headers, [-110] * 5)  # 평소 새벽 5시 10분 출발
    confirm_saving(client, headers, db_session, 4200)
    monkeypatch.setattr(car, "now_kst", at(datetime(*moment, tzinfo=KST)))

    speech = brief(client, headers, soc_now=soc, charger_kw=kw).json()["speech"]

    assert "평소처럼 내일 새벽 5시 10분 출발 기준으로" in speech
    assert len(sentences(speech)) == 3
    assert len(speech) <= MAX_SPEECH_CHARS


def test_parallel_briefings_make_one_record(concurrent):
    token = f"race-{uuid.uuid4()}"
    device_id = str(uuid.uuid4())
    setup = concurrent.session()
    try:
        setup.add(CarDevice(id=device_id, token_hash=hash_token(token)))
        setup.commit()
    finally:
        setup.close()

    def send(client) -> str | None:
        return client.post(URL, json=BODY, headers={"Authorization": f"Bearer {token}"}).json()[
            "saving_id"
        ]

    try:
        ids = concurrent.run(send, count=6)
        check = concurrent.session()
        try:
            count = check.scalar(select(func.count()).where(CarSaving.device_id == device_id))
        finally:
            check.close()
        assert len(set(ids)) == 1
        assert None not in ids
        assert count == 1
    finally:
        cleanup = concurrent.session()
        try:
            cleanup.execute(text("DELETE FROM car_devices WHERE id = :id"), {"id": device_id})
            cleanup.commit()
        finally:
            cleanup.close()


def test_departure_records_are_not_written_by_a_briefing(client, db_session):
    brief(client, register(client))

    assert list(db_session.scalars(select(CarDeparture))) == []


def test_briefings_keep_one_pending_record_and_never_push_out_a_plan(client, db_session):
    headers = register(client)
    plan = client.post(
        "/api/car/plan",
        json={**BODY, "plug_in_at": "2026-11-16T18:00", "depart_at": "2026-11-17T08:00"},
        headers=headers,
    ).json()
    for leak in range(19):  # 다른 출처 대기 기록을 20개까지 채운다
        client.post(
            "/api/car/plan",
            json={**BODY, "soc_now": 10 + leak, "depart_at": "2026-11-17T08:00"},
            headers=headers,
        )

    last = None
    for step in range(20):  # 잔량이 조금씩 다른 브리핑 20번
        last = brief(client, headers, soc_now=20 + step * 0.5).json()["saving_id"]

    pending = [s for s in savings(db_session) if s.confirmed_at is None]
    assert [s.id for s in pending if s.source == "briefing"] == [last]
    assert len([s for s in pending if s.source == "plan"]) == 20
    confirmed = client.post(f"/api/car/savings/{plan['saving_id']}/confirm", headers=headers)
    assert confirmed.status_code == 200


def test_a_confirmed_briefing_record_is_kept(client, db_session):
    headers = register(client)
    first = brief(client, headers).json()["saving_id"]
    assert client.post(f"/api/car/savings/{first}/confirm", headers=headers).status_code == 200

    second = brief(client, headers, soc_now=20).json()["saving_id"]

    assert second != first
    assert {s.id: s.confirmed_at is not None for s in savings(db_session)} == {
        first: True,
        second: False,
    }


@pytest.mark.parametrize(
    ("soc", "tonight_sentence"),
    [
        (32, "배터리가 32%라 오늘 밤 충전하세요."),
        (70, "배터리가 70%라 오늘 밤은 충전 안 해도 돼요."),
    ],
)
def test_year_end_without_next_years_holidays_drops_only_the_plan(
    client, db_session, monkeypatch, soc, tonight_sentence
):
    """2027-12-31 18:00: 내일(2028년) 공휴일 정보가 없다. 요금·절약 문장은 그대로 200."""
    headers = register(client)
    monkeypatch.setattr(car, "now_kst", at(datetime(2027, 12, 31, 18, 0, tzinfo=KST)))
    confirm_saving(client, headers, db_session, 4200)
    db_session.execute(
        text("UPDATE car_savings SET confirmed_at = :at"),
        {"at": datetime(2027, 12, 20, 9, 0, tzinfo=KST)},
    )

    response = brief(client, headers, soc_now=soc)

    assert response.status_code == 200
    body = response.json()
    assert body["price"]["band_label"] == "최대부하"
    assert body["actions"] == []
    assert body["saving_id"] is None
    assert body["tonight"]["reservation"] is None
    assert sentences(body["speech"]) == [
        "지금은 요금이 비싼 시간이고, 저녁 7시부터 싸져요.",
        tonight_sentence,
        "이번 달 와트잇으로 약 4,200원, 올해 약 4,200원 아꼈어요.",
    ]
    if soc < 50:
        assert body["assumptions"] == [
            "오늘 밤 충전 계획을 계산하지 못했어요: 2028년 공휴일 정보가 아직 없어서 요금을 "
            "계산할 수 없어요. 지금은 2026년, 2027년 날짜만 계산할 수 있어요."
        ]
