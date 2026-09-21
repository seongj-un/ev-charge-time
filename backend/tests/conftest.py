"""테스트 전역 conftest.

핵심 규칙: 테스트는 절대 개발 DB(``evcharge``)를 건드리지 않는다. 대신 별도의
``evcharge_test`` DB를 쓰고, 스키마는 세션당 한 번만 만든다. 각 테스트는
트랜잭션(+ SAVEPOINT) 안에서 돌고 끝나면 롤백해서 테스트끼리 데이터가 새지
않는다.

``DATABASE_URL`` 환경변수를 여기서 테스트 DB로 덮어써 둔다. 이러면 이
conftest를 거치지 않는 다른 모듈의 자체 fixture
(``tests/api/test_auth_deps.py`` 등 — 리뷰 중이라 수정 대상에서 제외)도
``get_settings()``/``os.environ.get("DATABASE_URL", ...)`` 조회를 통해 자동으로
테스트 DB를 보게 된다. 이게 개발 DB를 건드리는 걸 막는 핵심 장치다 — 그
파일도 예전 test_models.py와 똑같이 자기 engine fixture에서 drop_all을
하기 때문에, 리다이렉트가 없으면 여전히 개발 DB를 지워버린다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as DbSession

from evcharge.infra.db import Base, get_session
from evcharge.main import create_app
from evcharge.settings import get_settings

_SKIP_MSG = "PostgreSQL이 떠 있지 않습니다 (docker compose up -d db)"
_TEST_DB_NAME = "evcharge_test"


def _test_database_url() -> str:
    """테스트 DB URL. ``TEST_DATABASE_URL``이 있으면 그걸 그대로 쓴다 (CI용)."""
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        return override
    dev_url = get_settings().database_url
    parts = urlsplit(dev_url)
    return urlunsplit(parts._replace(path=f"/{_TEST_DB_NAME}"))


def _maintenance_url(test_url: str) -> str:
    """CREATE DATABASE는 자기 자신 DB에 접속한 채로는 못 하므로 postgres DB로."""
    parts = urlsplit(test_url)
    return urlunsplit(parts._replace(path="/postgres"))


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database() -> None:
    """세션 시작 시 딱 한 번: 테스트 DB가 없으면 만들고, DATABASE_URL을 돌린다.

    autouse라서 DB가 필요 없는 테스트(도메인 계산 등)에도 걸리므로, postgres가
    아예 안 떠 있어도 여기서는 절대 fail/skip하지 않는다 — 실제 "DB 필요한데
    없음" 판단은 이 DB를 실제로 쓰는 fixture(``test_engine`` 등)가 접속을
    시도할 때 한다. 그래야 도커 없이도 DB 무관 테스트는 그대로 돈다.
    """
    test_url = _test_database_url()
    os.environ["DATABASE_URL"] = test_url
    try:
        maintenance_engine = create_engine(
            _maintenance_url(test_url), isolation_level="AUTOCOMMIT"
        )
        with maintenance_engine.connect() as conn:
            db_name = urlsplit(test_url).path.lstrip("/")
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar()
            if not exists:
                # db_name은 우리가 만든 URL에서 나온 값이라 신뢰하지만, 식별자를
                # 그대로 문자열 포매팅하는 게 찜찜해서 최소한 따옴표만 이스케이프.
                conn.execute(text(f'CREATE DATABASE "{db_name.replace(chr(34), "")}"'))
        maintenance_engine.dispose()
    except Exception:
        # postgres가 안 떠 있거나 권한이 없거나 — 아래 test_engine이 알아서 skip한다.
        pass


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """테스트 DB에 붙는 세션 스코프 engine. 스키마는 세션당 한 번만 만든다."""
    test_url = _test_database_url()
    engine = create_engine(test_url, pool_pre_ping=True)
    try:
        engine.connect().close()
    except Exception:
        pytest.skip(_SKIP_MSG)

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[DbSession]:
    """테스트 하나당 트랜잭션 하나. 끝나면 무조건 롤백해서 깨끗한 상태를 보장한다.

    테스트 코드가 ``session.commit()``을 불러도(예: IntegrityError를 보려면
    커밋까지 가야 한다) 바깥 트랜잭션까지 끝나버리면 안 되므로, SAVEPOINT를
    계속 다시 열어주는 표준 SQLAlchemy 2.0 패턴을 쓴다.
    """
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    session = DbSession(bind=connection, expire_on_commit=False)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(session: DbSession, transaction) -> None:
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        event.remove(session, "after_transaction_end", _restart_savepoint)
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: DbSession) -> Iterator[TestClient]:
    """DB를 쓰는 라우터도 테스트에서는 같은 트랜잭션(db_session)을 보게 오버라이드.

    라우터가 커밋한 것도 테스트 쪽 ``db_session``으로 바로 보이고, 테스트가
    끝나면 db_session fixture가 통째로 롤백한다 — 이후 요청 헬퍼(로그인 등)를
    얹기 쉽도록 client와 db_session이 같은 트랜잭션을 공유하게 설계했다.
    """
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
