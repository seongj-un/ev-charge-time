"""DB 오류 문구(로그로 가는 것)에 쿼리 값이 들어가지 않는다."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError

from evcharge.domain.pricing import KST
from evcharge.infra import db

SECRET_DEVICE = "device-0f3c9a-not-in-logs"


@pytest.fixture
def app_engine(test_engine, monkeypatch):
    """앱이 쓰는 ``get_engine()``을 테스트 DB로 만든다."""
    monkeypatch.setenv("DATABASE_URL", test_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(db, "_engine", None)
    engine = db.get_engine()
    yield engine
    engine.dispose()


def test_app_engine_hides_parameters_in_errors(app_engine):
    """SQLAlchemy가 붙이는 값 목록만 가린다. PostgreSQL 자체의 DETAIL(제약 위반의 키 값)은
    그대로라, 그런 오류를 남기는 로그는 오류 종류만 적는다(``car_departures``)."""
    with app_engine.connect() as conn, pytest.raises(DataError) as caught:
        conn.execute(
            text("SELECT 1 / 0 AS boom, CAST(:device AS text), CAST(:at AS timestamptz)"),
            {"device": SECRET_DEVICE, "at": datetime(2026, 11, 19, 7, 31, tzinfo=KST)},
        )

    message = str(caught.value)
    assert "SELECT 1 / 0" in message  # 어떤 쿼리였는지는 남는다
    assert SECRET_DEVICE not in message
    assert "07:31" not in message
    assert "SQL parameters hidden" in message
