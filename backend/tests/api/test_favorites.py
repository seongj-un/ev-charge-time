"""F-14 즐겨찾는 충전소.

저장은 station_id만. 목록의 이름·주소는 charger_cache에서 읽는다. 캐시에
없는 station_id도 즐겨찾기 자체는 유효하므로 station_id만 채운 채 목록에
나온다 (F-07이 나중에 캐시를 채운다).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.domain.pricing import KST
from evcharge.infra.models import ChargerCache
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.models import User
from evcharge.infra.security import hash_password, hash_token, new_session_token


def _make_user(db_session, email="favorites@example.com") -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("password123"),
        nickname="테스터",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, db_session, user: User) -> None:
    token = new_session_token()
    db_session.add(
        SessionModel(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(KST) + timedelta(days=14),
        )
    )
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, token)


def test_put_favorite_returns_204_and_appears_in_list(client, db_session):
    user = _make_user(db_session)
    _login(client, db_session, user)

    response = client.put("/api/me/favorites/ST-001")
    assert response.status_code == 204

    listing = client.get("/api/me/favorites")
    assert listing.status_code == 200
    body = listing.json()
    assert len(body) == 1
    assert body[0]["station_id"] == "ST-001"


def test_put_favorite_twice_is_idempotent(client, db_session):
    user = _make_user(db_session)
    _login(client, db_session, user)

    assert client.put("/api/me/favorites/ST-001").status_code == 204
    assert client.put("/api/me/favorites/ST-001").status_code == 204

    body = client.get("/api/me/favorites").json()
    assert len(body) == 1


def test_favorite_list_uses_charger_cache_when_present(client, db_session):
    user = _make_user(db_session)
    _login(client, db_session, user)

    db_session.add(
        ChargerCache(
            station_id="ST-002",
            data={
                "name": "테스트 충전소",
                "address": "서울시 강남구",
                "lat": 37.5,
                "lng": 127.0,
                "distance_m": 100,
                "operator": "환경부",
                "available_hours": "24시간",
                "chargers": [],
            },
        )
    )
    db_session.commit()

    client.put("/api/me/favorites/ST-002")

    body = client.get("/api/me/favorites").json()
    assert len(body) == 1
    assert body[0]["station_id"] == "ST-002"
    assert body[0]["name"] == "테스트 충전소"
    assert body[0]["address"] == "서울시 강남구"


def test_favorite_without_cache_still_lists_with_station_id_only(client, db_session):
    user = _make_user(db_session)
    _login(client, db_session, user)

    client.put("/api/me/favorites/ST-003")

    body = client.get("/api/me/favorites").json()
    assert len(body) == 1
    assert body[0]["station_id"] == "ST-003"
    assert body[0]["name"] is None
    assert body[0]["address"] is None
    assert body[0]["chargers"] == []


def test_delete_favorite_returns_204_and_removes_from_list(client, db_session):
    user = _make_user(db_session)
    _login(client, db_session, user)

    client.put("/api/me/favorites/ST-004")

    response = client.delete("/api/me/favorites/ST-004")
    assert response.status_code == 204

    body = client.get("/api/me/favorites").json()
    assert body == []


def test_delete_favorite_not_favorited_returns_204(client, db_session):
    user = _make_user(db_session)
    _login(client, db_session, user)

    response = client.delete("/api/me/favorites/does-not-exist")
    assert response.status_code == 204


def test_favorites_are_scoped_to_user(client, db_session):
    user_a = _make_user(db_session, email="a@example.com")
    user_b = _make_user(db_session, email="b@example.com")

    _login(client, db_session, user_a)
    client.put("/api/me/favorites/ST-005")

    _login(client, db_session, user_b)
    body = client.get("/api/me/favorites").json()
    assert body == []


def test_unauthenticated_list_is_401(client):
    assert client.get("/api/me/favorites").status_code == 401


def test_unauthenticated_put_is_401(client):
    assert client.put("/api/me/favorites/ST-001").status_code == 401


def test_unauthenticated_delete_is_401(client):
    assert client.delete("/api/me/favorites/ST-001").status_code == 401
