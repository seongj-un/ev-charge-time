"""F-12 내 차량 (my vehicles) + /api/recommend의 vehicle_id 연동."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.domain.pricing import KST
from evcharge.infra.db import get_session
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.models import User, Vehicle
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


# ── I-2: DB 컬럼 길이 초과가 500으로 새면 안 된다 ───────────────────────────


def test_create_vehicle_name_over_column_length_is_422(auth_client):
    """vehicles.name은 varchar(100). 스키마에 max_length가 없으면 그대로 DB
    까지 내려가 StringDataRightTruncation → DataError → (고치기 전) 500이었다."""
    response = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "name": "차" * 200}
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


# ── A-1: 기본 차량 동시 설정 (IntegrityError 안전망) ──────────────────────


def test_concurrent_default_vehicle_creation_is_409_not_500(concurrent):
    """두 요청이 동시에 ``is_default: true``로 차량을 등록하면, 둘 다
    ``_clear_existing_default``(해제할 기존 기본이 없어 no-op)를 통과한 뒤
    동시에 INSERT해 부분 유니크 인덱스(uq_vehicles_one_default_per_user)를
    다툰다. 이 라우터엔 개별 IntegrityError 처리가 없으므로, 진 쪽이 A-1의
    안전망 없이는 500을 냈다."""
    session = concurrent.session()
    try:
        user = User(
            id=str(uuid.uuid4()),
            email=f"vehicle-race-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password("password123"),
            nickname="레이스",
        )
        session.add(user)
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

    def create_default_vehicle(client):
        client.cookies.set(SESSION_COOKIE, token)
        return client.post(
            "/api/me/vehicles", json={**VEHICLE, "is_default": True}
        ).status_code

    try:
        results = concurrent.run(create_default_vehicle, count=2)

        assert sorted(results) == [201, 409], (
            f"기본 차량 동시 생성 2건의 결과: {results}. 하나는 성공(201)하고, "
            "부분 유니크 인덱스를 위반한 쪽은 500이 아니라 409여야 한다(A-1)."
        )

        verify_session = concurrent.session()
        try:
            defaults = verify_session.scalars(
                select(Vehicle).where(
                    Vehicle.user_id == user_id, Vehicle.is_default.is_(True)
                )
            ).all()
        finally:
            verify_session.close()

        assert len(defaults) == 1, "기본 차량은 최종적으로 정확히 1대여야 한다"
    finally:
        cleanup_session = concurrent.session()
        try:
            cleanup_session.query(Vehicle).filter_by(user_id=user_id).delete()
            cleanup_session.query(SessionModel).filter_by(user_id=user_id).delete()
            cleanup_session.query(User).filter_by(id=user_id).delete()
            cleanup_session.commit()
        finally:
            cleanup_session.close()


# ── 부분 갱신 (C-2) ───────────────────────────────────────────────────────
# PATCH가 VehicleIn(is_default·mode에 기본값 있음)을 그대로 받던 시절엔,
# 이름만 바꾸려고 is_default를 빼고 보내면 기본값(False)이 실려 기존 기본
# 차량이 조용히 해제됐다. VehicleUpdate + exclude_unset=True로 실제로 보낸
# 필드만 반영하도록 고쳤다.


def test_patch_name_only_keeps_existing_default(auth_client):
    vehicle = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "is_default": True}
    ).json()

    updated = auth_client.patch(
        f"/api/me/vehicles/{vehicle['id']}", json={"name": "새 이름"}
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "새 이름"
    assert body["is_default"] is True, "is_default를 안 보냈으면 그대로 유지돼야 한다"
    assert body["battery_kwh"] == VEHICLE["battery_kwh"]
    assert body["charger_kw"] == VEHICLE["charger_kw"]


def test_patch_is_default_true_clears_existing_default(auth_client):
    """기존 동작 유지: is_default: true를 부분 PATCH로 보내도 기존 기본은 해제된다."""
    first = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "name": "1호차", "is_default": True}
    ).json()
    second = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "name": "2호차", "is_default": False}
    ).json()

    updated = auth_client.patch(
        f"/api/me/vehicles/{second['id']}", json={"is_default": True}
    )
    assert updated.status_code == 200
    assert updated.json()["is_default"] is True

    listed = {v["id"]: v for v in auth_client.get("/api/me/vehicles").json()}
    assert listed[first["id"]]["is_default"] is False
    assert listed[second["id"]]["is_default"] is True


def test_patch_empty_body_changes_nothing(auth_client):
    vehicle = auth_client.post(
        "/api/me/vehicles", json={**VEHICLE, "is_default": True}
    ).json()

    updated = auth_client.patch(f"/api/me/vehicles/{vehicle['id']}", json={})

    assert updated.status_code == 200
    assert updated.json() == vehicle


def test_patch_rejects_non_positive_values_when_sent(auth_client):
    vehicle = auth_client.post("/api/me/vehicles", json=VEHICLE).json()

    assert (
        auth_client.patch(
            f"/api/me/vehicles/{vehicle['id']}", json={"battery_kwh": 0}
        ).status_code
        == 422
    )
    assert (
        auth_client.patch(
            f"/api/me/vehicles/{vehicle['id']}", json={"charger_kw": -1}
        ).status_code
        == 422
    )


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


def test_recommend_explicit_charger_kw_wins_over_vehicle(auth_client):
    """D-3: battery_kwh는 이미 테스트가 있고 mode는 리뷰어가 수동 확인했지만,
    charger_kw는 요청 값이 차량 기본값을 이긴다는 테스트가 없었다."""
    vehicle = auth_client.post("/api/me/vehicles", json=VEHICLE).json()  # charger_kw=7

    default_response = auth_client.post(
        "/api/recommend", json={**RECOMMEND_BASE, "vehicle_id": vehicle["id"]}
    ).json()
    explicit_response = auth_client.post(
        "/api/recommend",
        json={**RECOMMEND_BASE, "vehicle_id": vehicle["id"], "charger_kw": 22},
    ).json()

    # energy_kwh(=battery_kwh 기반)는 charger_kw와 무관하게 그대로다.
    assert explicit_response["best"]["energy_kwh"] == pytest.approx(
        default_response["best"]["energy_kwh"]
    )

    def _duration(plan: dict) -> timedelta:
        start = datetime.fromisoformat(plan["start"])
        end = datetime.fromisoformat(plan["end"])
        return end - start

    # charger_kw가 차량 기본값(7kW)보다 훨씬 크면(22kW) 같은 에너지를 채우는
    # 시간이 눈에 띄게 짧아져야 한다 — 요청 값이 차량 기본값을 이겼다는 뜻이다.
    assert _duration(explicit_response["best"]) < _duration(default_response["best"])


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


@pytest.mark.parametrize("field", ["battery_kwh", "charger_kw"])
@pytest.mark.parametrize("value", ["Infinity", "NaN", 1e300])
def test_vehicle_numbers_must_be_finite_and_sane(auth_client, field, value):
    """차량 값은 저장됐다가 추천 계산으로 그대로 넘어간다 (F-12). 입구에서 막는다."""
    created = auth_client.post("/api/me/vehicles", json={**VEHICLE, field: value})
    assert created.status_code == 422

    vehicle = auth_client.post("/api/me/vehicles", json=VEHICLE).json()
    patched = auth_client.patch(f"/api/me/vehicles/{vehicle['id']}", json={field: value})
    assert patched.status_code == 422
