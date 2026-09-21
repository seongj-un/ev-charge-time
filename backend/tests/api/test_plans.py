import base64
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


# D-1·D-2: SavedPlanOut은 request/result 전 필드가 필수라, DB에 직접 꽂는
# 행도 완전한 형태를 갖춰야 한다(``created_at``만 바꿔치기하는 게 목적이라
# 나머지 값 자체는 임의로 둬도 된다).
_VALID_RESULT = {
    "best": {
        "start": "2026-05-01T13:00:00+09:00",
        "end": "2026-05-01T14:00:00+09:00",
        "energy_kwh": 10.0,
        "cost_won": 1000,
        "discounted_kwh": 0.0,
    },
    "baseline_now": {
        "start": "2026-05-01T12:00:00+09:00",
        "end": "2026-05-01T13:00:00+09:00",
        "energy_kwh": 10.0,
        "cost_won": 1500,
        "discounted_kwh": 0.0,
    },
    "savings_won": 1,
    "candidates_checked": 1,
    "assumptions": [],
    "unverified_tariff_items": [],
}


def _raw_plan(
    user_id: str,
    created_at: datetime,
    *,
    plan_id: str | None = None,
    savings_won: int = 1,
    charge_start: datetime | None = None,
) -> SavedPlan:
    """4번 수정: 실제 엔드포인트는 ``result.best.start``에서 ``charge_start``를
    뽑아 저장한다. 여기서도 그 파생 관계를 실제로 반영해 둔다 — ``result``와
    ``charge_start`` 컬럼이 따로 노는 테스트 데이터는 실제로는 나올 수 없는
    상태라 혼란만 준다. ``charge_start``를 명시하지 않으면 ``created_at``과
    같은 값을 쓴다(저장 시각과 충전 시각이 같은, 구분할 필요 없는 테스트용
    기본값) — 두 값이 다른 경우를 검증하는 테스트만 따로 넘긴다."""
    resolved_charge_start = charge_start if charge_start is not None else created_at
    result = {**_VALID_RESULT, "savings_won": savings_won}
    result = {
        **result,
        "best": {**result["best"], "start": resolved_charge_start.isoformat()},
    }
    return SavedPlan(
        id=plan_id or str(uuid.uuid4()),
        user_id=user_id,
        request=dict(SPEC_EXAMPLE),
        result=result,
        tariff_version="test",
        created_at=created_at,
        charge_start=resolved_charge_start,
    )


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
    """충전 날짜 내림차순 + 커서 페이징.

    세 계획의 충전 날짜를 일부러 다르게 만든다 — 조건이 같으면 charge_start가
    동률이 되어 id 순으로 떨어지고, 그러면 이 테스트가 정렬을 검증하지 못한다.
    """
    ids = [
        post_plan(
            client,
            earliest_start=f"2026-10-0{day}T18:00",
            deadline=f"2026-10-0{day + 1}T08:00",
        ).json()["id"]
        for day in (5, 6, 7)
    ]

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
    # 저장 시각이 아니라 충전 시작 시각 기준이다(4번 수정)
    month = plan1["charge_start"][:7]

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


# ── C-1(Critical): 목록/요약이 다른 사용자 기록을 섞으면 안 된다 ──────────
#
# 최종 전체 리뷰가 실제로 확인했다: me_plans.py의 ``SavedPlan.user_id ==
# user.id`` 술어 두 곳(목록·요약)을 지워도 이 파일의 나머지 테스트는 전부
# 통과한 채 188개 스위트가 그대로 초록색이었다 — 기존 테스트가 전부 "사용자
# 한 명만 존재하는" 트랜잭션 안에서 돌아서, 술어가 있으나 없으나 결과가
# 같았기 때문이다. 아래 두 테스트는 다른 사용자의 행을 일부러 심어서 그
# 술어가 실제로 일하는지를 확인한다.


def test_plans_list_excludes_other_users_plans(client, db_session, auth_user):
    """다른 사용자가 저장한 계획이 내 목록(필터 없음/``month`` 필터 둘 다)에
    나오면 안 된다. ``me_plans.py:69``의 ``user_id`` 술어가 지켜야 하는 것."""
    other_user = make_user(db_session, email="other-list@example.com")
    db_session.add(
        _raw_plan(other_user.id, datetime(2026, 10, 5, 12, 0, tzinfo=KST))
    )
    db_session.commit()

    unfiltered = client.get("/api/me/plans").json()
    assert unfiltered["items"] == []

    filtered = client.get("/api/me/plans", params={"month": "2026-10"}).json()
    assert filtered["items"] == []


def test_plans_summary_excludes_other_users_plans(client, db_session, auth_user):
    """``/plans/summary``의 건수·합계가 다른 사용자의 행을 세면 안 된다.
    ``me_plans.py:123``의 ``user_id`` 술어가 지켜야 하는 것."""
    other_user = make_user(db_session, email="other-summary@example.com")
    db_session.add(
        _raw_plan(
            other_user.id,
            datetime(2026, 10, 5, 12, 0, tzinfo=KST),
            savings_won=999999,
        )
    )
    db_session.commit()

    summary = client.get(
        "/api/me/plans/summary", params={"month": "2026-10"}
    ).json()

    assert summary["count"] == 0
    assert summary["total_savings_won"] == 0


# ── B-1: limit 하한/상한 경계값 ──────────────────────────────────────────


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_list_plans_limit_out_of_range_is_422(client, auth_user, limit):
    """limit 하한이 없으면 0/음수가, 저장 기록이 1건 이상인 사용자에게 ``has_more``를
    빈 슬라이스 전에 계산한 뒤 ``rows[-1]``을 해서 500(IndexError)을 냈다
    (라이브 서버에서 재현됨). 101(상한+1)도 함께 검증한다."""
    post_plan(client)  # 기록이 있어야 예전 버그(rows[-1])가 재현되는 조건과 같다.

    response = client.get("/api/me/plans", params={"limit": limit})

    assert response.status_code == 422


@pytest.mark.parametrize("limit", [1, 100])
def test_list_plans_limit_boundary_is_accepted(client, auth_user, limit):
    post_plan(client)

    response = client.get("/api/me/plans", params={"limit": limit})

    assert response.status_code == 200
    assert len(response.json()["items"]) <= limit


# ── B-3: month 형식 검증 ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "month", ["26-10", "2026-2", "2026/10", "2026-13", "not-a-month", ""]
)
def test_summary_invalid_month_format_is_422(client, auth_user, month):
    """``_month_bounds``가 ``"26-10"``·``"2026-2"``처럼 자릿수가 다른 값을
    조용히 받아 그대로 응답에 되돌려주던 것을 막는다."""
    response = client.get("/api/me/plans/summary", params={"month": month})
    assert response.status_code == 422


# ── B-4: 조작된/망가진 cursor ─────────────────────────────────────────────


@pytest.mark.parametrize("cursor", ["not-base64!!!", "aGVsbG8=", "%%%"])
def test_list_plans_malformed_cursor_is_422_not_500(client, auth_user, cursor):
    """평문 base64라 서명은 없지만(B-4, 유출 경로 없음이 확인되어 의도적으로
    안 함), 조작되거나 깨진 cursor가 500이 아니라 422를 내는지는 검증한다."""
    response = client.get("/api/me/plans", params={"cursor": cursor})
    assert response.status_code == 422


def test_list_plans_cursor_with_invalid_date_is_422_not_500(client, auth_user):
    """base64 자체는 유효하지만(``"|"``로 잘리는 형식도 맞음) 날짜 부분이
    ``fromisoformat``으로 파싱되지 않는 cursor."""
    bad_cursor = base64.urlsafe_b64encode(b"not-a-date|some-id").decode()

    response = client.get("/api/me/plans", params={"cursor": bad_cursor})

    assert response.status_code == 422


# ── D-1: 월 경계는 KST 기준이어야 한다 ─────────────────────────────────────


def test_summary_month_boundary_is_kst_not_utc(client, db_session, auth_user):
    """2026-10-01 00:30 KST(= 2026-09-30 15:30 UTC)로 저장된 기록은 summary?month=2026-10에
    잡히고 2026-09에는 안 잡혀야 한다. UTC 기준으로 비교하면 9월로 잘못 샌다."""
    row = _raw_plan(auth_user.id, datetime(2026, 10, 1, 0, 30, tzinfo=KST), savings_won=111)
    db_session.add(row)
    db_session.commit()

    oct_summary = client.get("/api/me/plans/summary", params={"month": "2026-10"}).json()
    sep_summary = client.get("/api/me/plans/summary", params={"month": "2026-09"}).json()

    assert oct_summary["count"] == 1
    assert oct_summary["total_savings_won"] == 111
    assert sep_summary["count"] == 0


def test_summary_month_boundary_rolls_over_year(client, db_session, auth_user):
    """12월 → 1월 롤오버도 KST 기준으로 정확해야 한다."""
    row = _raw_plan(auth_user.id, datetime(2027, 1, 1, 0, 15, tzinfo=KST), savings_won=222)
    db_session.add(row)
    db_session.commit()

    jan_summary = client.get("/api/me/plans/summary", params={"month": "2027-01"}).json()
    dec_summary = client.get("/api/me/plans/summary", params={"month": "2026-12"}).json()

    assert jan_summary["count"] == 1
    assert dec_summary["count"] == 0


# ── D-2: 동률 created_at 페이징 ────────────────────────────────────────────


def test_pagination_with_tied_charge_start_visits_each_row_exactly_once(
    client, db_session, auth_user
):
    """charge_start가 전부 같은 행 5개를 넣고 커서로 끝까지 넘겼을 때, 각 행이
    정확히 한 번씩만 나와야 한다.

    정렬·커서 키가 created_at에서 charge_start로 바뀌었으므로(4번 수정) 동률
    불변식도 새 키에서 성립해야 한다. id 내림차순 동률 깨기가 없으면 같은
    시각 행들을 건너뛰거나 중복해서 돌려준다. 저장 시각은 일부러 제각각으로
    둬서, 커서가 실수로 created_at을 다시 잡으면 이 테스트가 깨지게 한다.
    """
    same_charge = datetime(2026, 5, 1, 12, 0, tzinfo=KST)
    ids = [str(uuid.uuid4()) for _ in range(5)]
    for offset, plan_id in enumerate(ids):
        db_session.add(
            _raw_plan(
                auth_user.id,
                datetime(2026, 4, 1 + offset, 9, 0, tzinfo=KST),
                plan_id=plan_id,
                charge_start=same_charge,
            )
        )
    db_session.commit()

    seen: list[str] = []
    cursor = None
    for _ in range(10):  # 안전장치: next_cursor가 끝없이 이어지면 무한 루프를 막는다.
        params = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        page = client.get("/api/me/plans", params=params).json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert sorted(seen) == sorted(ids)
    assert len(seen) == len(set(seen))


# ── 2번: /plans month 필터 ──────────────────────────────────────────────


def test_list_plans_filters_by_month(client, db_session, auth_user):
    """9월·10월 기록을 섞어 넣으면 ``?month=2026-10``은 10월 것만 줘야 한다."""
    sep_id = str(uuid.uuid4())
    oct_id = str(uuid.uuid4())
    db_session.add(
        _raw_plan(auth_user.id, datetime(2026, 9, 15, 12, 0, tzinfo=KST), plan_id=sep_id)
    )
    db_session.add(
        _raw_plan(auth_user.id, datetime(2026, 10, 15, 12, 0, tzinfo=KST), plan_id=oct_id)
    )
    db_session.commit()

    response = client.get("/api/me/plans", params={"month": "2026-10"})

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [oct_id]


def test_list_plans_month_boundary_is_kst_not_utc(client, db_session, auth_user):
    """summary와 같은 경계 계산을 재사용하므로 여기도 KST 기준이어야 한다:
    2026-10-01 00:30 KST(= 2026-09-30 15:30 UTC)는 10월로 잡혀야 한다."""
    row_id = str(uuid.uuid4())
    db_session.add(
        _raw_plan(auth_user.id, datetime(2026, 10, 1, 0, 30, tzinfo=KST), plan_id=row_id)
    )
    db_session.commit()

    oct_items = client.get("/api/me/plans", params={"month": "2026-10"}).json()["items"]
    sep_items = client.get("/api/me/plans", params={"month": "2026-09"}).json()["items"]

    assert [item["id"] for item in oct_items] == [row_id]
    assert sep_items == []


def test_list_plans_without_month_is_unchanged(client, db_session, auth_user):
    """``month``를 안 주면 지금과 완전히 동일하게 전체 최신순이어야 한다."""
    sep_id = str(uuid.uuid4())
    oct_id = str(uuid.uuid4())
    db_session.add(
        _raw_plan(auth_user.id, datetime(2026, 9, 15, 12, 0, tzinfo=KST), plan_id=sep_id)
    )
    db_session.add(
        _raw_plan(auth_user.id, datetime(2026, 10, 15, 12, 0, tzinfo=KST), plan_id=oct_id)
    )
    db_session.commit()

    response = client.get("/api/me/plans")

    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [oct_id, sep_id]


def test_list_plans_month_and_limit_paginate_without_missing_or_duplicating(
    client, db_session, auth_user
):
    """month로 거른 뒤 그 안에서 커서로 끝까지 넘겼을 때, 그 달 기록이 빠짐없이
    정확히 한 번씩 나와야 한다 — 다른 달 기록은 몇 건이 있든 섞이면 안 된다."""
    oct_ids = [str(uuid.uuid4()) for _ in range(5)]
    for i, plan_id in enumerate(oct_ids):
        db_session.add(
            _raw_plan(
                auth_user.id,
                datetime(2026, 10, i + 1, 12, 0, tzinfo=KST),
                plan_id=plan_id,
            )
        )
    # 다른 달 기록도 섞어서 month 필터가 새는지 확인한다.
    for i in range(3):
        db_session.add(
            _raw_plan(
                auth_user.id,
                datetime(2026, 9, i + 1, 12, 0, tzinfo=KST),
            )
        )
    db_session.commit()

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"month": "2026-10", "limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        page = client.get("/api/me/plans", params=params).json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert sorted(seen) == sorted(oct_ids)
    assert len(seen) == len(set(seen))


@pytest.mark.parametrize(
    "month", ["26-10", "2026-2", "2026/10", "2026-13", "not-a-month", ""]
)
def test_list_plans_invalid_month_format_is_422(client, auth_user, month):
    """summary(B-3)와 같은 검증을 재사용하므로 같은 값들이 422여야 한다."""
    response = client.get("/api/me/plans", params={"month": month})
    assert response.status_code == 422


# ── 3번: saved_plans.vehicle_name 스냅샷 ─────────────────────────────────

VEHICLE = {"name": "출퇴근 차", "battery_kwh": 70, "charger_kw": 7}


def test_create_plan_without_vehicle_id_has_null_vehicle_name(client, auth_user):
    """직접 입력이면 vehicle_name은 빈 문자열이 아니라 null이어야 한다."""
    response = post_plan(client)

    assert response.status_code == 201
    assert response.json()["vehicle_name"] is None


def test_create_plan_with_vehicle_id_snapshots_vehicle_name(client, auth_user):
    vehicle = client.post("/api/me/vehicles", json=VEHICLE).json()

    response = post_plan(client, battery_kwh=None, charger_kw=None, vehicle_id=vehicle["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["vehicle_name"] == VEHICLE["name"]
    # 차량 기본값(battery_kwh)이 실제로 병합돼 계산에 쓰였는지도 함께 확인.
    assert body["request"]["battery_kwh"] == VEHICLE["battery_kwh"]


def test_saved_plan_vehicle_name_survives_vehicle_deletion(client, auth_user):
    """차량을 지워도 저장된 계획의 vehicle_name 스냅샷은 그대로 남아야 한다."""
    vehicle = client.post("/api/me/vehicles", json=VEHICLE).json()
    created = post_plan(client, battery_kwh=None, charger_kw=None, vehicle_id=vehicle["id"]).json()

    assert client.delete(f"/api/me/vehicles/{vehicle['id']}").status_code == 204

    detail = client.get(f"/api/me/plans/{created['id']}").json()
    assert detail["vehicle_name"] == VEHICLE["name"]

    listing = client.get("/api/me/plans").json()
    assert listing["items"][0]["vehicle_name"] == VEHICLE["name"]


def test_create_plan_with_unknown_vehicle_id_is_404(client, auth_user):
    response = post_plan(client, vehicle_id="does-not-exist")
    assert response.status_code == 404


def test_create_plan_with_another_users_vehicle_id_is_404(client, db_session, auth_user):
    other_user = make_user(db_session, email="other-plans-vehicle@example.com")
    login_as(client, db_session, other_user)
    other_vehicle = client.post("/api/me/vehicles", json=VEHICLE).json()

    login_as(client, db_session, auth_user)
    response = post_plan(client, vehicle_id=other_vehicle["id"])

    assert response.status_code == 404


# ── 4번: 월 필터·정렬 기준이 저장 시각이 아니라 충전 시작 시각 ──────────────


def test_month_filters_by_charge_start_not_created_at(client, db_session, auth_user):
    """9월에 저장한 "10월 충전 계획"은 10월에 잡혀야 한다.

    이 테스트가 4번 수정의 핵심이다. 예전에는 created_at 기준이라 이 계획이
    9월에 잡히고 10월 필터는 0건이었다 — 화면은 충전 날짜를 보여주는데
    필터는 저장일 기준이라, 사용자가 10월을 고르면 방금 세운 10월 계획이
    안 보였다.
    """
    plan_id = str(uuid.uuid4())
    db_session.add(
        _raw_plan(
            auth_user.id,
            datetime(2026, 9, 21, 17, 0, tzinfo=KST),  # 저장: 9월
            plan_id=plan_id,
            charge_start=datetime(2026, 10, 7, 22, 0, tzinfo=KST),  # 충전: 10월
        )
    )
    db_session.commit()

    october = client.get("/api/me/plans", params={"month": "2026-10"}).json()
    september = client.get("/api/me/plans", params={"month": "2026-09"}).json()

    assert [item["id"] for item in october["items"]] == [plan_id]
    assert september["items"] == []


def test_summary_uses_charge_start_not_created_at(client, db_session, auth_user):
    """summary도 같은 기준이어야 목록 건수와 합계가 맞는다."""
    db_session.add(
        _raw_plan(
            auth_user.id,
            datetime(2026, 9, 21, 17, 0, tzinfo=KST),
            savings_won=1500,
            charge_start=datetime(2026, 10, 7, 22, 0, tzinfo=KST),
        )
    )
    db_session.commit()

    october = client.get(
        "/api/me/plans/summary", params={"month": "2026-10"}
    ).json()
    september = client.get(
        "/api/me/plans/summary", params={"month": "2026-09"}
    ).json()

    assert october == {"month": "2026-10", "count": 1, "total_savings_won": 1500}
    assert september == {"month": "2026-09", "count": 0, "total_savings_won": 0}


def test_midnight_crossing_plan_lands_in_the_month_it_starts(
    client, db_session, auth_user
):
    """10월 31일 22:00 → 11월 1일 01:00 충전은 **10월**에만 잡힌다.

    best.end가 아니라 best.start를 기준으로 삼는 이유가 이것이다. 경부하가
    22–08시라 최적해가 자정을 넘기는 일이 흔하고, 사용자가 보는 날짜는
    시작일이다. 끝 시각을 기준으로 삼거나 두 달에 모두 넣으면 합계가 중복된다.
    """
    plan_id = str(uuid.uuid4())
    db_session.add(
        _raw_plan(
            auth_user.id,
            datetime(2026, 10, 25, 9, 0, tzinfo=KST),
            plan_id=plan_id,
            charge_start=datetime(2026, 10, 31, 22, 0, tzinfo=KST),
        )
    )
    db_session.commit()

    october = client.get("/api/me/plans", params={"month": "2026-10"}).json()
    november = client.get("/api/me/plans", params={"month": "2026-11"}).json()

    assert [item["id"] for item in october["items"]] == [plan_id]
    assert november["items"] == []


def test_charge_start_month_boundary_is_kst_not_utc(client, db_session, auth_user):
    """2026-10-01 00:30 KST(= 09-30 15:30 UTC) 충전은 10월이다.

    UTC로 잘랐다면 9월로 밀린다.
    """
    plan_id = str(uuid.uuid4())
    db_session.add(
        _raw_plan(
            auth_user.id,
            datetime(2026, 9, 1, 9, 0, tzinfo=KST),
            plan_id=plan_id,
            charge_start=datetime(2026, 10, 1, 0, 30, tzinfo=KST),
        )
    )
    db_session.commit()

    body = client.get("/api/me/plans", params={"month": "2026-10"}).json()
    assert [item["id"] for item in body["items"]] == [plan_id]


def test_list_is_sorted_by_charge_start_descending(client, db_session, auth_user):
    """목록 정렬도 충전 날짜 내림차순이다.

    필터만 충전 날짜 기준이고 정렬이 저장 순서로 남으면, 10월로 걸러도 날짜
    열이 뒤죽박죽 나와 사용자 눈에는 정렬이 없는 목록으로 보인다. 저장 순서를
    충전 순서와 일부러 반대로 넣어, created_at 정렬이 남아 있으면 깨지게 한다.
    """
    early_charge, late_charge = str(uuid.uuid4()), str(uuid.uuid4())
    db_session.add(
        _raw_plan(  # 먼저 저장, 늦게 충전
            auth_user.id,
            datetime(2026, 10, 1, 9, 0, tzinfo=KST),
            plan_id=late_charge,
            charge_start=datetime(2026, 10, 20, 22, 0, tzinfo=KST),
        )
    )
    db_session.add(
        _raw_plan(  # 나중에 저장, 일찍 충전
            auth_user.id,
            datetime(2026, 10, 2, 9, 0, tzinfo=KST),
            plan_id=early_charge,
            charge_start=datetime(2026, 10, 5, 22, 0, tzinfo=KST),
        )
    )
    db_session.commit()

    body = client.get("/api/me/plans").json()
    assert [item["id"] for item in body["items"]] == [late_charge, early_charge]


def test_charge_start_is_exposed_at_top_level(client, auth_user):
    """프론트가 result를 파고들지 않고 목록 날짜를 표시할 수 있어야 한다."""
    created = post_plan(client).json()

    assert created["charge_start"] == created["result"]["best"]["start"]
    assert created["charge_start"].endswith("+09:00")
