"""와트잇 BE-5 절감 기록: 계산 엔드포인트의 대기 기록."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from evcharge.api import car_savings
from evcharge.api.car_savings import MAX_PENDING_PER_DEVICE, record_pending
from evcharge.api.routes import car
from evcharge.domain.pricing import KST
from evcharge.infra.models import CarDevice, CarSaving

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
