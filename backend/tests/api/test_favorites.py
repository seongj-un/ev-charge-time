"""F-14 즐겨찾는 충전소.

저장은 station_id만. 목록의 이름·주소는 charger_cache에서 읽는다. 캐시에
없는 station_id도 즐겨찾기 자체는 유효하므로 station_id만 채운 채 목록에
나온다 (F-07이 나중에 캐시를 채운다).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.domain.pricing import KST
from evcharge.infra.models import ChargerCache, FavoriteStation
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


# ── D-4: 즐겨찾기 캐시 필드 ──────────────────────────────────────────────


def test_favorite_list_cache_fields_are_populated_on_cache_hit(client, db_session):
    """캐시 적중 시 name·address뿐 아니라 lat·lng·distance_m·operator·
    available_hours도 제대로 채워지는지 확인한다(기존 테스트는 name·address만
    봤다)."""
    user = _make_user(db_session)
    _login(client, db_session, user)

    db_session.add(
        ChargerCache(
            station_id="ST-006",
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

    client.put("/api/me/favorites/ST-006")

    body = client.get("/api/me/favorites").json()
    assert len(body) == 1
    station = body[0]
    assert station["lat"] == 37.5
    assert station["lng"] == 127.0
    assert station["distance_m"] == 100
    assert station["operator"] == "환경부"
    assert station["available_hours"] == "24시간"


def test_favorite_list_cache_fields_are_null_on_cache_miss(client, db_session):
    """캐시 미적중이면 캐시 유래 필드가 빈 문자열/0이 아니라 명시적으로
    None(JSON null)이어야 한다 — F-07이 아직 501이라 즐겨찾기 목록은 당분간
    대부분 캐시 미적중으로 나가므로, 빈 값 기본값으로 바뀌면 조용히 회귀한다."""
    user = _make_user(db_session)
    _login(client, db_session, user)

    client.put("/api/me/favorites/ST-007")

    body = client.get("/api/me/favorites").json()
    assert len(body) == 1
    station = body[0]
    assert station["station_id"] == "ST-007"
    assert station["name"] is None
    assert station["address"] is None
    assert station["lat"] is None
    assert station["lng"] is None
    assert station["distance_m"] is None
    assert station["operator"] is None
    assert station["available_hours"] is None
    assert station["chargers"] == []


# ── A-3/B-2: 즐겨찾기 PUT 동시 요청 ─────────────────────────────────────────


def test_concurrent_put_favorite_is_idempotent(concurrent):
    """멱등 PUT은 동시 요청에서도 500/409 등 에러를 내면 안 된다(B-2).

    check-then-insert였을 때는 여러 요청이 모두 '존재하지 않음'을 확인하고
    지나간 뒤 동시에 INSERT를 시도하면, 하나만 성공하고 나머지는 복합 PK
    위반으로 IntegrityError(→ 그 전엔 500, A-1 이후엔 409)를 냈다 — 리뷰어가
    두 세션으로 실제 재현했다. A-3의 ``concurrent`` 픽스처(get_session 오버라이드
    없는 진짜 앱 + 진짜 스레드)로만 재현 가능한 경쟁이다.
    """
    session = concurrent.session()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=f"fav-race-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password("password123"),
            nickname="레이스",
        )
        session.add(user)
        # User↔Session 사이에는 ORM relationship()이 없어(순수 FK 컬럼만) 같은
        # flush에 함께 넣으면 유닛오브워크가 삽입 순서를 보장하지 않는다 —
        # users insert 전에 sessions insert가 나가 FK 위반이 날 수 있다.
        # 커밋을 나눠 그 문제를 피한다(이 파일의 _login 헬퍼와 같은 패턴).
        session.commit()
        user_id = user.id

        token = new_session_token()
        session.add(
            SessionModel(
                id=str(uuid.uuid4()),
                user_id=user_id,
                token_hash=hash_token(token),
                expires_at=datetime.now(KST) + timedelta(days=14),
            )
        )
        session.commit()
    finally:
        session.close()

    station_id = f"ST-RACE-{uuid.uuid4().hex}"

    def put_favorite(client):
        client.cookies.set(SESSION_COOKIE, token)
        return client.put(f"/api/me/favorites/{station_id}").status_code

    try:
        results = concurrent.run(put_favorite, count=8)

        assert results == [204] * 8, (
            f"동시 PUT 8건 중 일부가 204가 아니다: {results}. 멱등 PUT은 "
            "경쟁 중에도 항상 204여야 한다."
        )

        verify_session = concurrent.session()
        try:
            rows = verify_session.scalars(
                select(FavoriteStation).where(
                    FavoriteStation.user_id == user_id,
                    FavoriteStation.station_id == station_id,
                )
            ).all()
        finally:
            verify_session.close()

        assert len(rows) == 1, (
            f"동시 PUT {len(results)}건 후 즐겨찾기 행이 {len(rows)}개 — 정확히 "
            "1개여야 중복 저장이 안 된 것이다."
        )
    finally:
        cleanup_session = concurrent.session()
        try:
            cleanup_session.query(FavoriteStation).filter_by(
                user_id=user_id, station_id=station_id
            ).delete()
            cleanup_session.query(SessionModel).filter_by(user_id=user_id).delete()
            cleanup_session.query(User).filter_by(id=user_id).delete()
            cleanup_session.commit()
        finally:
            cleanup_session.close()
