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
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TypeVar
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from evcharge.infra.db import Base, get_session
from evcharge.main import create_app
from evcharge.settings import get_settings

_T = TypeVar("_T")

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
    except SQLAlchemyError:
        # postgres가 안 떠 있거나 권한이 없거나 — 여기서 보고하지 않는 이유는
        # 곧이어 test_engine이 같은 원인으로 실패하면서 훨씬 정확한 skip 메시지를
        # 내놓기 때문이다. 여기서 먼저 떠들면 같은 사실을 두 번, 그것도 덜 친절한
        # 문구로 알리게 된다. 삼키는 범위는 SQLAlchemyError로 좁혀 두어
        # 오타·타입 오류 같은 진짜 버그는 그대로 터지게 한다.
        pass


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """테스트 DB에 붙는 세션 스코프 engine. 스키마는 세션당 한 번만 만든다."""
    test_url = _test_database_url()
    engine = create_engine(test_url, pool_pre_ping=True)
    try:
        engine.connect().close()
    except SQLAlchemyError:
        # 접속 실패만 skip으로 바꾼다. 그 밖의 예외는 설정 실수이므로 그대로 터뜨린다.
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
def client(request: pytest.FixtureRequest) -> Iterator[TestClient]:
    """DB를 쓰는 라우터도 테스트에서는 같은 트랜잭션(db_session)을 보게 오버라이드.

    예전에는 이 fixture가 인자로 ``db_session``을 직접 받아서, ``client``를 쓰는
    테스트는 전부 (실제로 DB를 건드리는지와 무관하게) ``test_engine``의 접속
    시도를 강제로 거쳐 Postgres가 없으면 스킵됐다. ``/health``·``/api/timeline``·
    ``/api/recommend``·스텁 라우터는 애초에 ``get_session``에 의존하지 않으므로
    이 요구가 불필요했다.

    그래서 여기서는 ``get_session``을 즉시 db_session으로 바꿔치기하지 않고,
    실제로 그 의존성을 요청하는 핸들러가 호출될 때만
    ``request.getfixturevalue("db_session")``으로 지연 평가한다. DB를 쓰지 않는
    요청은 이 클로저 자체가 안 불리니 Postgres 유무와 무관하게 돌고, DB를 쓰는
    요청에서 처음 호출되는 순간 ``db_session``(→ ``test_engine``)이 그제서야
    연결을 시도해 없으면 그 테스트만 스킵된다. ``getfixturevalue``는 pytest가
    캐시해 주므로 같은 테스트 안에서 여러 요청이 같은 세션(=같은 트랜잭션)을
    계속 보게 된다 — 라우터가 커밋한 것도 테스트 쪽 ``db_session``으로 바로
    보이고, 테스트가 끝나면 db_session fixture가 통째로 롤백하는 기존 설계는
    그대로 유지된다.
    """
    app = create_app()

    def _lazy_db_session() -> Iterator[DbSession]:
        yield request.getfixturevalue("db_session")

    app.dependency_overrides[get_session] = _lazy_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@dataclass
class ConcurrentRequests:
    """진짜 동시 요청을 재현하는 헬퍼(A-3).

    ``client``/``db_session``은 테스트 하나당 커넥션 하나를 SAVEPOINT로 감싸
    공유하는 구조라, 여러 요청을 보내도 실제로는 같은 커넥션·같은 트랜잭션을
    순차적으로 타므로 진짜 경쟁(서로 다른 커넥션이 동시에 같은 행을 읽고 쓰는
    상황)을 재현할 수 없다. 잠금 경쟁(로그인 실패 카운터) 검증을 위해 처음
    만들었던 패턴 — ``get_session`` 오버라이드가 없는 진짜 앱을 만들어 요청마다
    프로덕션과 똑같이 새 커넥션을 열게 하고, 그 위에 여러 OS 스레드로 동시에
    요청을 보내는 것 — 을 여기로 승격해서 재사용 가능하게 한다.
    """

    app: FastAPI
    engine: Engine

    def client(self) -> TestClient:
        """독립 쿠키 저장소를 가진 새 ``TestClient``. 스레드마다 하나씩 써야
        한다 — 같은 클라이언트를 여러 스레드가 공유하면 쿠키 jar가 섞인다."""
        return TestClient(self.app)

    def session(self) -> DbSession:
        """``get_session`` 오버라이드 없이, 셋업·검증·정리용으로 직접 여는
        진짜 커넥션 세션. ``db_session``(SAVEPOINT) 픽스처를 거치지 않으므로
        여기서 커밋한 것은 테스트가 끝나도 자동으로 롤백되지 않는다 — 호출자가
        직접 지워야 한다."""
        return DbSession(bind=self.engine)

    def run(
        self, fn: Callable[[TestClient], _T], count: int, timeout: float = 15.0
    ) -> list[_T]:
        """``fn``을 ``count``개의 진짜 스레드에서, 스레드마다 독립 클라이언트로
        동시에 실행하고 결과를 모아 돌려준다(완료 순서 — 요청 자체가 서로
        무순서로 겹치는 것이 목적이므로 호출 순서를 보장하지 않는다)."""
        results: list[_T] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def _worker() -> None:
            try:
                result = fn(self.client())
            except BaseException as exc:  # noqa: BLE001 - 스레드 예외를 메인으로 옮기려는 의도
                with lock:
                    errors.append(exc)
                return
            with lock:
                results.append(result)

        threads = [threading.Thread(target=_worker) for _ in range(count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=timeout)
            assert not t.is_alive(), "동시 요청 스레드가 제한 시간 안에 끝나지 않았다"

        if errors:
            raise errors[0]

        return results


@pytest.fixture
def concurrent(test_engine: Engine) -> ConcurrentRequests:
    """``get_session`` 오버라이드가 없는 진짜 앱 + 진짜 엔진으로 동시 요청을
    보낼 수 있게 해주는 픽스처. 사용법은 ``ConcurrentRequests`` 참고."""
    return ConcurrentRequests(app=create_app(), engine=test_engine)
