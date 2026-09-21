import inspect
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..settings import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_session() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


@contextmanager
def session_scope(
    overrides: Mapping[Callable[..., object], Callable[..., object]] | None = None,
) -> Iterator[Session]:
    """``Depends(get_session)`` 없이, 정말 필요할 때만 세션을 여는 컨텍스트 매니저.

    ``/api/recommend``처럼 요청 본문을 봐야 DB가 필요한지 알 수 있는 라우트를 위한
    것이다 — FastAPI는 ``Depends()``로 선언된 의존성을 요청마다 무조건 해석하므로,
    조건부로 열려면 ``Depends`` 선언 자체를 포기하고 라우터 코드에서 직접 열어야
    한다(1번 수정).

    ``overrides``에 ``app.dependency_overrides``를 넘기면 테스트가 ``get_session``에
    걸어둔 오버라이드(SAVEPOINT로 감싼 트랜잭션 세션)를 그대로 재사용한다. 이게
    없으면 테스트와 다른 새 커넥션을 열게 되어, 같은 테스트 트랜잭션 안에서 만든
    데이터(아직 커밋되지 않아 다른 커넥션에는 안 보임)를 못 찾는 문제가 생긴다.

    오버라이드가 제너레이터 함수(``get_session``·테스트의 지연 평가 버전)면 그
    프로토콜대로 끝까지 돌려 정리(cleanup)를 보장하고, 테스트에서 흔한 "세션을
    바로 돌려주는 평범한 함수" 오버라이드(예: ``lambda: db_session``)면 정리할
    것이 없으므로 그대로 값만 넘긴다 — 어느 쪽이든 호출자가 쓰던 세션을 여기서
    임의로 닫아버리면 같은 테스트의 다음 요청이 이미 닫힌 세션을 보게 된다.
    """
    provider: Callable[..., object] = get_session
    if overrides:
        provider = overrides.get(get_session, get_session)

    if inspect.isgeneratorfunction(provider):
        gen = provider()
        session = next(gen)
        try:
            yield session
        finally:
            next(gen, None)
    else:
        yield provider()
