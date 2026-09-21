import uuid
from datetime import datetime

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import pytest

from evcharge.domain.pricing import KST
from evcharge.infra.models import ChargerCache, FavoriteStation, SavedPlan, User, Vehicle

# engine/db_session은 tests/conftest.py의 공용 fixture를 쓴다 (evcharge_test DB,
# 세션당 스키마 1회 생성, 테스트별 트랜잭션 롤백). 여기서 더는 drop_all을 하지
# 않는다 — 예전 버전은 개발 DB(evcharge)에 붙어서 매 실행마다 테이블을 지웠다.


def make_user(session: Session, email="a@example.com") -> User:
    user = User(id=str(uuid.uuid4()), email=email, password_hash="x", nickname="충전러")
    session.add(user)
    session.commit()
    return user


def test_all_five_tables_exist(test_engine):
    tables = set(inspect(test_engine).get_table_names())
    assert {
        "users",
        "vehicles",
        "saved_plans",
        "favorite_stations",
        "charger_cache",
    } <= tables


def test_email_is_unique(db_session):
    make_user(db_session, "dup@example.com")
    db_session.add(
        User(id=str(uuid.uuid4()), email="dup@example.com", password_hash="y")
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_deleting_a_user_removes_their_data(db_session):
    user = make_user(db_session, "cascade@example.com")
    db_session.add_all(
        [
            Vehicle(
                id=str(uuid.uuid4()),
                user_id=user.id,
                name="출퇴근 차",
                battery_kwh=70.0,
                charger_kw=7.0,
                mode="self_low",
                is_default=True,
            ),
            SavedPlan(
                id=str(uuid.uuid4()),
                user_id=user.id,
                request={"soc_now": 30},
                result={"savings_won": 399},
                tariff_version="2026.1-draft",
                charge_start=datetime(2026, 10, 7, 22, 0, tzinfo=KST),
            ),
            FavoriteStation(user_id=user.id, station_id="ST-001"),
        ]
    )
    db_session.commit()

    db_session.delete(user)
    db_session.commit()

    assert db_session.scalars(select(Vehicle)).all() == []
    assert db_session.scalars(select(SavedPlan)).all() == []
    assert db_session.scalars(select(FavoriteStation)).all() == []


def test_only_one_default_vehicle_per_user(db_session):
    user = make_user(db_session, "default@example.com")
    for name in ("차 1", "차 2"):
        db_session.add(
            Vehicle(
                id=str(uuid.uuid4()),
                user_id=user.id,
                name=name,
                battery_kwh=70.0,
                charger_kw=7.0,
                is_default=True,
            )
        )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_favorite_station_pair_is_unique(db_session):
    user = make_user(db_session, "fav@example.com")
    db_session.add(FavoriteStation(user_id=user.id, station_id="ST-009"))
    db_session.commit()

    db_session.add(FavoriteStation(user_id=user.id, station_id="ST-009"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_charger_cache_holds_json(db_session):
    db_session.add(ChargerCache(station_id="ST-100", data={"name": "빛가람 충전소"}))
    db_session.commit()

    cached = db_session.get(ChargerCache, "ST-100")
    assert cached.data["name"] == "빛가람 충전소"
