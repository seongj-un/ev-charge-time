"""F-12 내 차량 (my vehicles) + /api/recommend의 vehicle_id 연동."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.domain.pricing import KST
from evcharge.infra.db import get_session
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.models import User
from evcharge.infra.security import hash_password, hash_token, new_session_token
from evcharge.main import create_app

VEHICLE = {"name": "출퇴근 차", "battery_kwh": 70, "charger_kw": 7}

RECOMMEND_BASE = {
    "soc_now": 30,
    "soc_target": 60,
    "earliest_start": "2026-10-07T18:00",
    "deadline": "2026-10-08T08:00",
}


def make_user(db_session, email: str) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("password123"),
        nickname="테스터",
    )
    db_session.add(user)
    db_session.commit()
    return user


def login_as(client, db_session, user: User) -> None:
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


def make_client(db_session) -> TestClient:
    """db_session과 같은 트랜잭션을 보되 쿠키 jar는 독립인 클라이언트.

    ``client`` fixture 하나를 auth_client/other_auth_client가 함께 쓰면 쿠키
    jar가 공유되어 두 번째 로그인이 첫 번째를 덮어써 버린다. 사용자별로
    분리된 TestClient가 필요하다.
    """
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app)


@pytest.fixture
def user(db_session) -> User:
    return make_user(db_session, "vehicles-owner@example.com")


@pytest.fixture
def other_user(db_session) -> User:
    return make_user(db_session, "vehicles-other@example.com")


@pytest.fixture
def auth_client(db_session, user):
    c = make_client(db_session)
    login_as(c, db_session, user)
    return c


@pytest.fixture
def other_auth_client(db_session, other_user):
    c = make_client(db_session)
    login_as(c, db_session, other_user)
    return c


# ── 등록/목록 ──────────────────────────────────────────────────────────


def test_create_vehicle_returns_201_and_appears_in_list(auth_client):
    response = auth_client.post("/api/me/vehicles", json=VEHICLE)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == VEHICLE["name"]
    assert body["battery_kwh"] == VEHICLE["battery_kwh"]
    assert body["charger_kw"] == VEHICLE["charger_kw"]
    assert body["mode"] == "self_low"
    assert body["is_default"] is False
    assert "id" in body

    listed = auth_client.get("/api/me/vehicles")
    assert listed.status_code == 200
    assert [v["id"] for v in listed.json()] == [body["id"]]


def test_create_vehicle_requires_login(client):
    response = client.post("/api/me/vehicles", json=VEHICLE)
    assert response.status_code == 401


def test_list_vehicles_requires_login(client):
    response = client.get("/api/me/vehicles")
    assert response.status_code == 401


def test_create_vehicle_rejects_non_positive_battery(auth_client):
    response = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "battery_kwh": 0}
    )
    assert response.status_code == 422


def test_create_vehicle_rejects_non_positive_charger(auth_client):
    response = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "charger_kw": 0}
    )
    assert response.status_code == 422


# ── 기본 차량 단일성 ────────────────────────────────────────────────────


def test_second_default_vehicle_clears_the_first(auth_client):
    first = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "name": "1호차", "is_default": True}
    ).json()
    second = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "name": "2호차", "is_default": True}
    ).json()

    assert second["is_default"] is True

    listed = {v["id"]: v for v in auth_client.get("/api/me/vehicles").json()}
    assert listed[first["id"]]["is_default"] is False
    assert listed[second["id"]]["is_default"] is True


def test_updating_default_moves_it_to_the_edited_vehicle(auth_client):
    first = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "name": "1호차", "is_default": True}
    ).json()
    second = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "name": "2호차", "is_default": False}
    ).json()

    updated = auth_client.patch(
        f"/api/me/vehicles/{second['id']}",
        json={**VEHICLE, "name": "2호차", "is_default": True},
    )
    assert updated.status_code == 200
    assert updated.json()["is_default"] is True

    listed = {v["id"]: v for v in auth_client.get("/api/me/vehicles").json()}
    assert listed[first["id"]]["is_default"] is False
    assert listed[second["id"]]["is_default"] is True


# ── 소유권 (다른 사용자 → 404) ───────────────────────────────────────────


def test_get_another_users_vehicle_in_list_does_not_leak(auth_client, other_auth_client):
    other_auth_client.post("/api/me/vehicles", json=VEHICLE)

    listed = auth_client.get("/api/me/vehicles").json()
    assert listed == []


def test_patch_another_users_vehicle_is_404(auth_client, other_auth_client):
    other_vehicle = other_auth_client.post("/api/me/vehicles", json=VEHICLE).json()

    response = auth_client.patch(
        f"/api/me/vehicles/{other_vehicle['id']}", json=VEHICLE
    )
    assert response.status_code == 404


def test_delete_another_users_vehicle_is_404(auth_client, other_auth_client):
    other_vehicle = other_auth_client.post("/api/me/vehicles", json=VEHICLE).json()

    response = auth_client.delete(f"/api/me/vehicles/{other_vehicle['id']}")
    assert response.status_code == 404


def test_unknown_vehicle_id_is_404(auth_client):
    assert auth_client.patch("/api/me/vehicles/does-not-exist", json=VEHICLE).status_code == 404
    assert auth_client.delete("/api/me/vehicles/does-not-exist").status_code == 404


def test_delete_vehicle_removes_it(auth_client):
    created = auth_client.post("/api/me/vehicles", json=VEHICLE).json()

    response = auth_client.delete(f"/api/me/vehicles/{created['id']}")
    assert response.status_code == 204

    assert auth_client.get("/api/me/vehicles").json() == []


# ── /api/recommend 연동 ──────────────────────────────────────────────────


def test_recommend_with_vehicle_id_uses_vehicle_defaults(auth_client):
    vehicle = auth_client.post("/api/me/vehicles", json=VEHICLE).json()

    response = auth_client.post(
        "/api/recommend", json={**RECOMMEND_BASE, "vehicle_id": vehicle["id"]}
    )

    assert response.status_code == 200
    body = response.json()
    # energy_kwh = battery_kwh(70) * (60-30)/100 = 21.0
    assert body["best"]["energy_kwh"] == pytest.approx(21.0)


def test_recommend_explicit_value_wins_over_vehicle(auth_client):
    vehicle = auth_client.post("/api/me/vehicles", json=VEHICLE).json()

    response = auth_client.post(
        "/api/recommend",
        json={
            **RECOMMEND_BASE,
            "vehicle_id": vehicle["id"],
            "battery_kwh": 100,
        },
    )

    assert response.status_code == 200
    body = response.json()
    # energy_kwh = battery_kwh(100, explicit) * (60-30)/100 = 30.0
    assert body["best"]["energy_kwh"] == pytest.approx(30.0)


def test_recommend_with_another_users_vehicle_id_is_404(auth_client, other_auth_client):
    other_vehicle = other_auth_client.post("/api/me/vehicles", json=VEHICLE).json()

    response = auth_client.post(
        "/api/recommend", json={**RECOMMEND_BASE, "vehicle_id": other_vehicle["id"]}
    )
    assert response.status_code == 404


def test_recommend_with_vehicle_id_requires_login(client):
    response = client.post(
        "/api/recommend", json={**RECOMMEND_BASE, "vehicle_id": "some-id"}
    )
    assert response.status_code == 401
