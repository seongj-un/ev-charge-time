"""와트잇 BE-5 절감 기록: 계산 엔드포인트의 대기 기록."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from evcharge.api import car_savings
from evcharge.api.car_savings import MAX_PENDING_PER_DEVICE, record_pending
from evcharge.api.routes import car
from evcharge.domain.pricing import KST
from evcharge.infra.models import CarDevice, CarSaving
from evcharge.infra.security import hash_token

# 2026-11-16(월) 18:00, 겨울 평일 최대부하. 밤 10시까지 기다리면 아낀다.
MONDAY_EVENING = datetime(2026, 11, 16, 18, 0, tzinfo=KST)
PLAN = {"soc_now": 20, "battery_capacity_wh": 77400, "depart_at": "2026-11-17T08:00"}
PUBLIC_LEAK = {
    "place": "public",
    "soc_now": 30,
    "battery_capacity_wh": 70000,
    "payment": "nonmember",
    "charger_speed": "slow",
}


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(car, "now_kst", lambda: MONDAY_EVENING)
    monkeypatch.delenv("CAR_LEAK_MIN_WON", raising=False)


def register(client) -> dict[str, str]:
    body = client.post("/api/car/devices").json()
    return {"Authorization": f"Bearer {body['device_token']}"}


def savings(db_session) -> list[CarSaving]:
    return list(db_session.scalars(select(CarSaving).order_by(CarSaving.created_at)))


def test_plan_without_token_is_unchanged_and_writes_nothing(client, db_session):
    body = client.post("/api/car/plan", json=PLAN).json()

    assert body["savings_won"] > 0
    assert body["saving_id"] is None
    assert savings(db_session) == []


def test_plan_with_a_wrong_token_still_computes(client, db_session):
    plain = client.post("/api/car/plan", json=PLAN).json()
    wrong = client.post(
        "/api/car/plan", json=PLAN, headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert wrong.status_code == 200
    assert wrong.json() == plain
    assert savings(db_session) == []


def test_plan_with_a_device_token_records_a_pending_saving(client, db_session):
    headers = register(client)
    body = client.post("/api/car/plan", json=PLAN, headers=headers).json()

    (row,) = savings(db_session)
    assert body["saving_id"] == row.id
    assert row.cause == "time"
    assert row.source == "plan"
    assert row.savings_won == body["savings_won"]
    assert row.energy_kwh == pytest.approx(body["plan"]["energy_kwh"])
    assert row.confirmed_at is None
    # 기록 말고는 응답이 토큰 없을 때와 같다.
    plain = client.post("/api/car/plan", json=PLAN).json()
    assert {**body, "saving_id": None} == plain


def test_plan_without_savings_records_nothing(client, db_session, monkeypatch):
    # 일요일은 하루 종일 경부하라 아끼는 돈이 0원이다.
    monkeypatch.setattr(car, "now_kst", lambda: datetime(2026, 11, 15, 18, tzinfo=KST))
    body = client.post(
        "/api/car/plan",
        json={**PLAN, "depart_at": "2026-11-16T07:00"},
        headers=register(client),
    ).json()

    assert body["savings_won"] == 0
    assert body["saving_id"] is None
    assert savings(db_session) == []


def test_leak_check_records_only_when_leaking(client, db_session):
    headers = register(client)

    leaking = client.post("/api/car/leak-check", json=PUBLIC_LEAK, headers=headers).json()
    member = client.post(
        "/api/car/leak-check", json={**PUBLIC_LEAK, "payment": "member"}, headers=headers
    ).json()

    (row,) = savings(db_session)
    assert leaking["saving_id"] == row.id
    assert row.cause == "payment"
    assert row.source == "leak_check"
    assert row.savings_won == leaking["leak_won"]
    assert row.energy_kwh == pytest.approx(leaking["energy_kwh"])
    assert member["leaking"] is False
    assert member["saving_id"] is None


def test_leak_check_home_records_cause_time(client, db_session):
    body = client.post(
        "/api/car/leak-check",
        json={"soc_now": 20, "battery_capacity_wh": 77400, "depart_at": "2026-11-17T08:00"},
        headers=register(client),
    ).json()

    assert body["leaking"] is True
    (row,) = savings(db_session)
    assert (row.id, row.cause, row.source) == (body["saving_id"], "time", "leak_check")


def test_recording_failure_never_fails_the_calculation(client, db_session, monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(car_savings, "record_pending", broken)
    response = client.post("/api/car/plan", json=PLAN, headers=register(client))

    assert response.status_code == 200
    assert response.json()["savings_won"] > 0
    assert response.json()["saving_id"] is None


def _device(db_session) -> CarDevice:
    device = CarDevice(id=str(uuid.uuid4()), token_hash=uuid.uuid4().hex * 2)
    db_session.add(device)
    db_session.commit()
    return device


def _record(db_session, device, won=1000) -> str:
    return record_pending(
        db_session, device, cause="time", savings_won=won, energy_kwh=10.0, source="plan"
    )


def test_saving_is_capped_at_100000_won(db_session):
    device = _device(db_session)
    saving_id = _record(db_session, device, won=150_000)

    assert db_session.get(CarSaving, saving_id).savings_won == 100_000


def test_only_the_latest_20_pending_savings_are_kept(db_session):
    device = _device(db_session)
    other = _device(db_session)
    confirmed_id = _record(db_session, device)
    db_session.get(CarSaving, confirmed_id).confirmed_at = MONDAY_EVENING
    db_session.commit()
    other_id = _record(db_session, other)

    ids = [_record(db_session, device) for _ in range(MAX_PENDING_PER_DEVICE + 5)]

    pending = set(
        db_session.scalars(
            select(CarSaving.id).where(
                CarSaving.device_id == device.id, CarSaving.confirmed_at.is_(None)
            )
        )
    )
    assert pending == set(ids[-MAX_PENDING_PER_DEVICE:])
    # 확정된 기록과 다른 기기의 기록은 지우지 않는다.
    assert db_session.get(CarSaving, confirmed_id) is not None
    assert db_session.get(CarSaving, other_id) is not None
    total = db_session.scalar(select(func.count()).select_from(CarSaving))
    assert total == MAX_PENDING_PER_DEVICE + 2


# ── 확정과 합산 ────────────────────────────────────────────────────────

NONE_SPEECH = "아직 아낀 기록이 없어요. 와트잇 추천대로 충전하면 여기에 쌓여요."
NOTE = "추천을 따랐을 때 아낀 금액(서버 계산값)이며 실제 청구 요금과 다를 수 있습니다."


def kst(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


def summary(client, headers, **params):
    return client.get("/api/car/savings/summary", headers=headers, params=params)


def device_of(db_session, headers) -> CarDevice:
    from evcharge.infra.security import hash_token

    token = headers["Authorization"].removeprefix("Bearer ")
    return db_session.scalar(select(CarDevice).where(CarDevice.token_hash == hash_token(token)))


def confirmed(db_session, device, won, at, cause="time") -> None:
    db_session.add(
        CarSaving(
            id=str(uuid.uuid4()),
            device_id=device.id,
            cause=cause,
            savings_won=won,
            energy_kwh=10.0,
            source="plan",
            confirmed_at=at,
        )
    )
    db_session.commit()


def test_pending_then_confirmed_then_summed(client):
    headers = register(client)
    plan = client.post("/api/car/plan", json=PLAN, headers=headers).json()

    before = summary(client, headers).json()
    assert before["month_count"] == 0  # 대기 기록은 합산에 들어가지 않는다

    response = client.post(f"/api/car/savings/{plan['saving_id']}/confirm", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["saving_id"] == plan["saving_id"]
    assert body["savings_won"] == plan["savings_won"]
    assert body["cause"] == "time" and body["source"] == "plan"
    assert body["confirmed_at"] == "2026-11-16T18:00:00+09:00"

    after = summary(client, headers).json()
    won = plan["savings_won"]
    assert after == {
        "month": "2026-11",
        "month_won": won,
        "month_count": 1,
        "year": 2026,
        "year_won": won,
        "year_count": 1,
        "total_won": won,
        "by_cause": {"time_won": won, "payment_won": 0},
        "speech": f"이번 달 와트잇으로 약 {won:,}원, 올해 약 {won:,}원 아꼈어요.",
        "note": NOTE,
    }


def test_confirm_is_idempotent(client, monkeypatch):
    headers = register(client)
    saving_id = client.post("/api/car/plan", json=PLAN, headers=headers).json()["saving_id"]

    first = client.post(f"/api/car/savings/{saving_id}/confirm", headers=headers).json()
    monkeypatch.setattr(car, "now_kst", lambda: kst(2026, 11, 16, 23))
    second = client.post(f"/api/car/savings/{saving_id}/confirm", headers=headers)

    assert second.status_code == 200
    assert second.json() == first  # 확정 시각도 처음 그대로
    assert summary(client, headers).json()["month_count"] == 1


def test_confirm_another_devices_saving_is_404(client, db_session):
    mine = register(client)
    theirs = register(client)
    saving_id = client.post("/api/car/plan", json=PLAN, headers=mine).json()["saving_id"]

    response = client.post(f"/api/car/savings/{saving_id}/confirm", headers=theirs)

    assert response.status_code == 404
    assert db_session.get(CarSaving, saving_id).confirmed_at is None


@pytest.mark.parametrize("saving_id", [str(uuid.uuid4()), "not-a-uuid", "1' OR '1'='1"])
def test_confirm_unknown_saving_is_404(client, saving_id):
    response = client.post(f"/api/car/savings/{saving_id}/confirm", headers=register(client))

    assert response.status_code == 404
    assert response.json() == {"detail": "절감 기록을 찾을 수 없습니다."}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic abc"}],
)
def test_savings_endpoints_need_a_valid_device_token(client, headers):
    saving_id = str(uuid.uuid4())
    for response in (
        client.post(f"/api/car/savings/{saving_id}/confirm", headers=headers),
        summary(client, headers),
    ):
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert isinstance(response.json()["detail"], str)


def test_summary_without_records_says_so(client):
    body = summary(client, register(client)).json()

    assert body["month"] == "2026-11"
    assert body["month_won"] == body["year_won"] == body["total_won"] == 0
    assert body["speech"] == NONE_SPEECH
    assert body["note"] == NOTE


def test_summary_counts_only_this_devices_confirmed_records(client, db_session):
    mine = register(client)
    theirs = register(client)
    confirmed(db_session, device_of(db_session, theirs), 5000, kst(2026, 11, 10))
    record_pending(
        db_session, device_of(db_session, mine), cause="time", savings_won=7000,
        energy_kwh=10.0, source="plan",
    )

    assert summary(client, mine).json()["total_won"] == 0


def test_month_and_year_boundaries_are_kst(client, db_session):
    headers = register(client)
    device = device_of(db_session, headers)
    # KST 2026-12-31 23:59:59 = UTC 14:59:59, KST 2027-01-01 00:00 = UTC 2026-12-31 15:00
    confirmed(db_session, device, 1000, kst(2026, 12, 31, 23, 59, 59))
    confirmed(db_session, device, 2000, kst(2027, 1, 1, 0, 0))
    # KST 2026-12-01 00:00은 12월이다 (UTC로는 11월 30일 15:00).
    confirmed(db_session, device, 400, kst(2026, 12, 1, 0, 0), cause="payment")
    confirmed(db_session, device, 30, kst(2026, 11, 30, 23, 59))

    december = summary(client, headers, month="2026-12").json()
    january = summary(client, headers, month="2027-01").json()
    november = summary(client, headers, month="2026-11").json()

    assert (december["month_won"], december["month_count"]) == (1400, 2)
    assert (december["year"], december["year_won"], december["year_count"]) == (2026, 1430, 3)
    assert (january["month_won"], january["year"], january["year_won"]) == (2000, 2027, 2000)
    assert (november["month_won"], november["month_count"]) == (30, 1)
    assert december["total_won"] == january["total_won"] == 3430
    assert december["by_cause"] == {"time_won": 3030, "payment_won": 400}


def test_summary_speech_labels_other_months_and_years(client, db_session, monkeypatch):
    monkeypatch.setattr(car, "now_kst", lambda: kst(2027, 1, 5, 8))
    headers = register(client)
    device = device_of(db_session, headers)
    confirmed(db_session, device, 8400, kst(2026, 12, 20))
    confirmed(db_session, device, 1200, kst(2027, 1, 3))

    this_month = summary(client, headers).json()
    last_month = summary(client, headers, month="2026-12").json()
    empty_month = summary(client, headers, month="2027-02").json()

    assert this_month["month"] == "2027-01"
    assert this_month["speech"] == "이번 달 와트잇으로 약 1,200원, 올해 약 1,200원 아꼈어요."
    assert last_month["speech"] == (
        "2026년 12월 와트잇으로 약 8,400원, 2026년 한 해 약 8,400원 아꼈어요."
    )
    assert empty_month["speech"] == (
        "2월에는 아낀 기록이 없어요. 지금까지 와트잇으로 약 9,600원 아꼈어요."
    )


@pytest.mark.parametrize("month", ["2026-13", "26-11", "2026-1", "november"])
def test_summary_month_must_be_yyyy_mm(client, month):
    response = summary(client, register(client), month=month)

    assert response.status_code == 422
    assert response.json() == {"detail": "month는 YYYY-MM 형식이어야 합니다."}


def test_device_last_seen_moves_on_use(client, db_session):
    headers = register(client)
    device = device_of(db_session, headers)
    device.last_seen_at = kst(2026, 1, 1)
    db_session.commit()

    summary(client, headers)

    db_session.expire_all()
    assert device_of(db_session, headers).last_seen_at > kst(2026, 1, 1)


# ── 확정 남용 막기: 72시간 기한, 하루 3건 ───────────────────────────────

def new_saving(client, headers) -> str:
    return client.post("/api/car/plan", json=PLAN, headers=headers).json()["saving_id"]


def confirm_saving(client, headers, saving_id: str):
    return client.post(f"/api/car/savings/{saving_id}/confirm", headers=headers)


def age(db_session, saving_id: str, interval: str) -> None:
    """기록을 DB 시계 기준으로 ``interval``만큼 오래된 것으로 만든다."""
    db_session.execute(
        text(
            "UPDATE car_savings SET created_at = clock_timestamp() - CAST(:age AS interval) "
            "WHERE id = :id"
        ),
        {"age": interval, "id": saving_id},
    )
    db_session.commit()


def test_confirm_window_is_72_hours(client, db_session):
    headers = register(client)
    fresh, old = new_saving(client, headers), new_saving(client, headers)
    age(db_session, fresh, "71 hours 59 minutes")
    age(db_session, old, "72 hours 1 minute")

    assert client.post(f"/api/car/savings/{fresh}/confirm", headers=headers).status_code == 200
    expired = client.post(f"/api/car/savings/{old}/confirm", headers=headers)
    assert expired.status_code == 410
    assert expired.json() == {"detail": "이 기록은 확정할 수 있는 기간(72시간)이 지났습니다."}
    assert db_session.get(CarSaving, old).confirmed_at is None


def test_fourth_confirm_of_the_day_is_429_and_works_the_next_day(client, monkeypatch):
    headers = register(client)
    ids = [new_saving(client, headers) for _ in range(4)]

    for saving_id in ids[:3]:
        assert confirm_saving(client, headers, saving_id).status_code == 200
    fourth = confirm_saving(client, headers, ids[3])

    assert fourth.status_code == 429
    assert fourth.json() == {
        "detail": "오늘 확정할 수 있는 횟수(3건)를 다 썼습니다. 내일 다시 확정해 주세요."
    }
    # 18:00 → 다음 날 0시(KST)까지 6시간
    assert fourth.headers["retry-after"] == "21600"
    # 이미 확정한 기록을 다시 부르는 것은 한도를 쓰지 않는다.
    again = confirm_saving(client, headers, ids[0])
    assert again.status_code == 200

    monkeypatch.setattr(car, "now_kst", lambda: kst(2026, 11, 17, 0, 0))
    assert confirm_saving(client, headers, ids[3]).status_code == 200
    november = summary(client, headers).json()
    assert november["month_count"] == 4


def test_daily_confirm_max_comes_from_settings(client, monkeypatch):
    monkeypatch.setenv("CAR_SAVINGS_DAILY_CONFIRM_MAX", "1")
    headers = register(client)
    first, second = new_saving(client, headers), new_saving(client, headers)

    assert client.post(f"/api/car/savings/{first}/confirm", headers=headers).status_code == 200
    assert client.post(f"/api/car/savings/{second}/confirm", headers=headers).status_code == 429


def test_parallel_confirms_never_pass_the_daily_limit(concurrent, monkeypatch):
    monkeypatch.setattr(car, "now_kst", lambda: MONDAY_EVENING)
    token = f"race-{uuid.uuid4()}"
    device_id = str(uuid.uuid4())
    saving_ids = [str(uuid.uuid4()) for _ in range(6)]

    setup = concurrent.session()
    try:
        setup.add(CarDevice(id=device_id, token_hash=hash_token(token)))
        setup.flush()
        for saving_id in saving_ids:
            setup.add(
                CarSaving(
                    id=saving_id, device_id=device_id, cause="time", savings_won=1000,
                    energy_kwh=10.0, source="plan",
                )
            )
        setup.commit()
    finally:
        setup.close()

    queue = list(saving_ids)
    lock = threading.Lock()

    def confirm_one(client) -> int:
        with lock:
            saving_id = queue.pop()
        return client.post(
            f"/api/car/savings/{saving_id}/confirm",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code

    try:
        codes = concurrent.run(confirm_one, count=len(saving_ids))
        assert sorted(codes) == [200, 200, 200, 429, 429, 429]
        check = concurrent.session()
        try:
            confirmed_count = check.scalar(
                select(func.count()).where(
                    CarSaving.device_id == device_id, CarSaving.confirmed_at.is_not(None)
                )
            )
        finally:
            check.close()
        assert confirmed_count == 3
    finally:
        cleanup = concurrent.session()
        try:
            cleanup.execute(text("DELETE FROM car_devices WHERE id = :id"), {"id": device_id})
            cleanup.commit()
        finally:
            cleanup.close()
