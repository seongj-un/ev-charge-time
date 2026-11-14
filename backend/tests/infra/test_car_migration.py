"""와트잇 BE-5 마이그레이션(c4e8a1f2b7d3)을 실제 PostgreSQL에서 올리고 내린다.

테스트 공용 DB(``evcharge_test``)는 ``create_all``로 스키마를 만들어서 마이그레이션
파일을 거치지 않는다. 그래서 여기서는 빈 DB(``evcharge_test_migrations``)를 따로
만들어 ``alembic upgrade head`` → ``downgrade`` → ``upgrade``를 돌리고, 마이그레이션이
만든 스키마가 모델과 같은지(autogenerate 비교)까지 본다. 끝나면 그 DB를 지운다.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from evcharge.infra.db import Base

BACKEND = Path(__file__).resolve().parents[2]
DB_NAME = "evcharge_test_migrations"
PREVIOUS = "e557028bf5dd"
CAR_TABLES = {
    "car_devices",
    "car_savings",
    "car_device_rate_limits",
    "car_voice_rate_limits",
    "car_voice_service_quota",
}


def _url_with_db(url: str, name: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{name}"))


@pytest.fixture
def migration_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    # conftest가 DATABASE_URL을 evcharge_test로 돌려 둔다. 같은 서버의 빈 DB를 쓴다.
    base = os.environ["DATABASE_URL"]
    admin = create_engine(_url_with_db(base, "postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME}"))
            conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
    except SQLAlchemyError:
        admin.dispose()
        pytest.skip("PostgreSQL이 떠 있지 않습니다")

    url = _url_with_db(base, DB_NAME)
    monkeypatch.setenv("DATABASE_URL", url)
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME} WITH (FORCE)"))
        admin.dispose()


def _alembic() -> Config:
    """alembic.ini 없이 만든 설정. env.py가 DATABASE_URL(settings)에서 주소를 읽는다.

    ini 파일을 넘기면 env.py가 ``fileConfig``로 로깅을 다시 설정하면서 이미 있는
    로거를 꺼 버린다(``disable_existing_loggers``). 그러면 뒤에 도는 다른 테스트의
    ``caplog``가 아무것도 못 받는다.
    """
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return config


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_car_tables_migrate_up_down_and_up_again(migration_db):
    config = _alembic()

    command.upgrade(config, "head")
    assert _tables(migration_db) >= CAR_TABLES

    command.downgrade(config, PREVIOUS)
    tables = _tables(migration_db)
    assert not CAR_TABLES & tables
    assert {"users", "saved_plans", "chat_service_quota"} <= tables

    command.upgrade(config, "head")
    assert _tables(migration_db) >= CAR_TABLES


def test_voice_quota_migration_goes_down_alone(migration_db):
    """BE-3 리비전만 되돌리면 음성 카운터 두 테이블만 사라지고 BE-5 테이블은 남는다."""
    config = _alembic()
    command.upgrade(config, "head")

    command.downgrade(config, "c4e8a1f2b7d3")
    tables = _tables(migration_db)
    assert not {"car_voice_rate_limits", "car_voice_service_quota"} & tables
    assert {"car_devices", "car_savings", "car_device_rate_limits"} <= tables

    command.upgrade(config, "head")
    assert _tables(migration_db) >= CAR_TABLES


def test_migrated_car_schema_matches_the_models(migration_db):
    command.upgrade(_alembic(), "head")
    engine = create_engine(migration_db)
    try:
        with engine.connect() as conn:
            diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()

    def touches_car_table(diff) -> bool:
        flat = diff if isinstance(diff, tuple) else diff[0]
        return any(getattr(item, "name", None) in CAR_TABLES or (
            getattr(getattr(item, "table", None), "name", None) in CAR_TABLES
        ) or item in CAR_TABLES for item in flat)

    assert [d for d in diffs if touches_car_table(d)] == []


def test_migrated_constraints_reject_bad_rows(migration_db):
    command.upgrade(_alembic(), "head")
    engine = create_engine(migration_db)
    device_id = str(uuid.uuid4())
    insert_saving = text(
        "INSERT INTO car_savings (id, device_id, cause, savings_won, energy_kwh, source) "
        "VALUES (:id, :device, :cause, :won, 10, :source)"
    )
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO car_devices (id, token_hash) VALUES (:id, :h)"),
                {"id": device_id, "h": "a" * 64},
            )
        for cause, won, source in [
            ("time", 100_001, "plan"),
            ("time", -1, "plan"),
            ("weather", 10, "plan"),
            ("time", 10, "manual"),
        ]:
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(
                    insert_saving,
                    {"id": str(uuid.uuid4()), "device": device_id, "cause": cause,
                     "won": won, "source": source},
                )
        with engine.begin() as conn:
            conn.execute(
                insert_saving,
                {"id": str(uuid.uuid4()), "device": device_id, "cause": "payment",
                 "won": 100_000, "source": "leak_check"},
            )
            # 기기를 지우면 기록도 함께 지워진다 (ON DELETE CASCADE).
            conn.execute(text("DELETE FROM car_devices WHERE id = :id"), {"id": device_id})
            assert conn.execute(text("SELECT count(*) FROM car_savings")).scalar_one() == 0
    finally:
        engine.dispose()
