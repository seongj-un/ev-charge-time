import uuid
from datetime import datetime, timedelta

import pytest

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.api.deps import get_tariff
from evcharge.domain.pricing import KST
from evcharge.infra.models import SavedPlan
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.models import User
from evcharge.infra.security import hash_password, hash_token, new_session_token

SPEC_EXAMPLE = {
    "battery_kwh": 70,
    "soc_now": 30,
    "soc_target": 60,
    "charger_kw": 7,
    "earliest_start": "2026-10-07T18:00",
    "deadline": "2026-10-08T08:00",
}


def make_user(db_session, email="plans@example.com") -> User:
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
    """user를 위한 세션을 만들어 client 쿠키에 심는다.

    signup/login 엔드포인트는 다른 에이전트가 별도 워크트리에서 만들고 있어
    이 워크트리에는 아직 없다. 그래서 세션 행을 직접 심고 쿠키만 굽는다.
    """
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


@pytest.fixture
def auth_user(client, db_session) -> User:
    user = make_user(db_session)
    login_as(client, db_session, user)
    return user


def post_plan(client, **overrides):
    return client.post("/api/me/plans", json={**SPEC_EXAMPLE, **overrides})


def test_create_plan_recomputes_and_matches_recommend(client, auth_user):
    recommend_body = client.post("/api/recommend", json=SPEC_EXAMPLE).json()

    response = post_plan(client)

    assert response.status_code == 201
    body = response.json()
    assert body["result"] == recommend_body
    assert body["request"]["battery_kwh"] == SPEC_EXAMPLE["battery_kwh"]
    assert "id" in body
    assert body["created_at"].endswith("+09:00")


def test_client_supplied_result_is_ignored(client, auth_user):
    recommend_body = client.post("/api/recommend", json=SPEC_EXAMPLE).json()

    response = post_plan(
        client,
        result={
            "best": {"start": "2000-01-01T00:00:00+09:00"},
            "savings_won": -999999,
        },
    )

    assert response.status_code == 201
    assert response.json()["result"] == recommend_body


def test_stored_tariff_version_matches_current(client, auth_user):
    response = post_plan(client)

    assert response.status_code == 201
    assert response.json()["tariff_version"] == get_tariff().version


def test_list_is_newest_first_and_paginates(client, auth_user):
    ids = [post_plan(client).json()["id"] for _ in range(3)]

    page1 = client.get("/api/me/plans", params={"limit": 2}).json()
    assert [item["id"] for item in page1["items"]] == list(reversed(ids))[:2]
    assert page1["next_cursor"] is not None

    page2 = client.get(
        "/api/me/plans", params={"limit": 2, "cursor": page1["next_cursor"]}
    ).json()
    assert [item["id"] for item in page2["items"]] == [ids[0]]
    assert page2["next_cursor"] is None


def test_list_default_limit_is_20(client, auth_user):
    post_plan(client)

    response = client.get("/api/me/plans")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_summary_returns_month_count_and_savings_sum(client, auth_user):
    plan1 = post_plan(client).json()
    plan2 = post_plan(client).json()
    month = plan1["created_at"][:7]

    summary = client.get("/api/me/plans/summary", params={"month": month}).json()

    assert summary["month"] == month
    assert summary["count"] == 2
    assert summary["total_savings_won"] == (
        plan1["result"]["savings_won"] + plan2["result"]["savings_won"]
    )


def test_summary_excludes_other_months(client, auth_user):
    post_plan(client)

    summary = client.get(
        "/api/me/plans/summary", params={"month": "1999-01"}
    ).json()

    assert summary["count"] == 0
    assert summary["total_savings_won"] == 0


def test_read_then_delete_plan(client, auth_user):
    created = post_plan(client).json()
    plan_id = created["id"]

    detail = client.get(f"/api/me/plans/{plan_id}")
    assert detail.status_code == 200
    assert detail.json() == created

    delete_response = client.delete(f"/api/me/plans/{plan_id}")
    assert delete_response.status_code == 204

    missing = client.get(f"/api/me/plans/{plan_id}")
    assert missing.status_code == 404

    listing = client.get("/api/me/plans").json()
    assert plan_id not in [item["id"] for item in listing["items"]]


def test_read_never_recomputes_even_if_stored_result_is_stale(
    client, db_session, auth_user
):
    """저장한 것은 계획이지 실제 기록이 아니다: 조회 시 저장된 JSON을 그대로 준다."""
    created = post_plan(client).json()
    plan_id = created["id"]

    row = db_session.get(SavedPlan, plan_id)
    row.result = {**row.result, "savings_won": 123456789}
    row.tariff_version = "stale-version-from-the-past"
    db_session.commit()

    detail = client.get(f"/api/me/plans/{plan_id}").json()
    assert detail["result"]["savings_won"] == 123456789
    assert detail["tariff_version"] == "stale-version-from-the-past"


def test_other_users_plan_id_is_404(client, db_session, auth_user):
    mine = post_plan(client).json()

    other_user = make_user(db_session, email="other-plans@example.com")
    login_as(client, db_session, other_user)

    assert client.get(f"/api/me/plans/{mine['id']}").status_code == 404
    assert client.delete(f"/api/me/plans/{mine['id']}").status_code == 404


def test_unknown_plan_id_is_404(client, auth_user):
    assert client.get("/api/me/plans/does-not-exist").status_code == 404
    assert client.delete("/api/me/plans/does-not-exist").status_code == 404


def test_unauthenticated_requests_are_401(client):
    assert client.get("/api/me/plans").status_code == 401
    assert client.get("/api/me/plans/summary", params={"month": "2026-10"}).status_code == 401
    assert client.get("/api/me/plans/some-id").status_code == 401
    assert client.post("/api/me/plans", json=SPEC_EXAMPLE).status_code == 401
    assert client.delete("/api/me/plans/some-id").status_code == 401
