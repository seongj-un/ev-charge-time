import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from evcharge.api.auth_deps import SESSION_COOKIE, current_user
from evcharge.domain.pricing import KST
from evcharge.infra.db import get_session
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.models import User
from evcharge.infra.security import hash_token, new_session_token

# engine/db_session은 tests/conftest.py의 공용 fixture를 쓴다 (evcharge_test DB,
# 세션당 스키마 1회 생성, 테스트별 트랜잭션 롤백) — tests/infra/test_models.py와
# 같은 이유로, 이 파일도 더 이상 자체 drop_all/create_all을 하지 않는다.


@pytest.fixture
def auth_client(db_session):
    """current_user 하나만 붙은 최소 앱. 실제 라우터는 아직 이 의존성을 쓰지 않는다."""
    app = FastAPI()
    app.dependency_overrides[get_session] = lambda: db_session

    @app.get("/whoami")
    def whoami(user: User = Depends(current_user)):
        return {"id": user.id, "email": user.email}

    return TestClient(app)


def make_user(db_session, email="auth-deps@example.com") -> User:
    user = User(id=str(uuid.uuid4()), email=email, password_hash="x", nickname="테스터")
    db_session.add(user)
    db_session.commit()
    return user


def make_session(db_session, user, *, expired=False) -> str:
    token = new_session_token()
    delta = timedelta(days=-1) if expired else timedelta(days=14)
    db_session.add(
        SessionModel(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(KST) + delta,
        )
    )
    db_session.commit()
    return token


def test_valid_session_cookie_returns_the_user(auth_client, db_session):
    user = make_user(db_session)
    token = make_session(db_session, user)
    auth_client.cookies.set(SESSION_COOKIE, token)

    response = auth_client.get("/whoami")

    assert response.status_code == 200
    assert response.json() == {"id": user.id, "email": user.email}


def test_missing_cookie_is_401(auth_client):
    response = auth_client.get("/whoami")

    assert response.status_code == 401


def test_unknown_token_is_401(auth_client):
    auth_client.cookies.set(SESSION_COOKIE, "not-a-real-token")

    response = auth_client.get("/whoami")

    assert response.status_code == 401


def test_expired_session_is_401(auth_client, db_session):
    user = make_user(db_session, email="auth-deps-expired@example.com")
    token = make_session(db_session, user, expired=True)
    auth_client.cookies.set(SESSION_COOKIE, token)

    response = auth_client.get("/whoami")

    assert response.status_code == 401
