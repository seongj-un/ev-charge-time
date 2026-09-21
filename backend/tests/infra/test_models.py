import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from evcharge.infra.db import Base
from evcharge.infra.models import ChargerCache, FavoriteStation, SavedPlan, User, Vehicle
from evcharge.settings import get_settings


@pytest.fixture(scope="module")
def engine():
    url = os.environ.get("DATABASE_URL", get_settings().database_url)
    engine = create_engine(url)
    try:
        engine.connect().close()
    except Exception:
        pytest.skip("PostgreSQL이 떠 있지 않습니다 (docker compose up -d db)")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session
        session.rollback()


def make_user(session, email="a@example.com") -> User:
    user = User(id=str(uuid.uuid4()), email=email, password_hash="x", nickname="충전러")
    session.add(user)
    session.commit()
    return user


def test_all_five_tables_exist(engine):
    tables = set(inspect(engine).get_table_names())
    assert {
        "users",
        "vehicles",
        "saved_plans",
        "favorite_stations",
        "charger_cache",
    } <= tables


def test_email_is_unique(session):
    make_user(session, "dup@example.com")
    session.add(
        User(id=str(uuid.uuid4()), email="dup@example.com", password_hash="y")
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_a_user_removes_their_data(session, engine):
    user = make_user(session, "cascade@example.com")
    session.add_all(
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
            ),
            FavoriteStation(user_id=user.id, station_id="ST-001"),
        ]
    )
    session.commit()

    session.delete(user)
    session.commit()

    assert session.scalars(select(Vehicle)).all() == []
    assert session.scalars(select(SavedPlan)).all() == []
    assert session.scalars(select(FavoriteStation)).all() == []


def test_only_one_default_vehicle_per_user(session):
    user = make_user(session, "default@example.com")
    for name in ("차 1", "차 2"):
        session.add(
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
        session.commit()


def test_favorite_station_pair_is_unique(session):
    user = make_user(session, "fav@example.com")
    session.add(FavoriteStation(user_id=user.id, station_id="ST-009"))
    session.commit()

    session.add(FavoriteStation(user_id=user.id, station_id="ST-009"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_charger_cache_holds_json(session):
    session.add(ChargerCache(station_id="ST-100", data={"name": "빛가람 충전소"}))
    session.commit()

    cached = session.get(ChargerCache, "ST-100")
    assert cached.data["name"] == "빛가람 충전소"
