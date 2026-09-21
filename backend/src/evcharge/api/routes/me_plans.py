"""F-13 충전 기록(저장한 추천 계획).

``routes/me.py``가 다른 엔드포인트(내 정보·차량·즐겨찾기)의 스텁을 담고 있고
다른 에이전트가 그 파일을 동시에 건드리고 있어, 저장한 계획 엔드포인트는
별도 라우터로 뺐다. ``main.py``에 나란히 등록한다.

저장한 계획은 "계획"이지 실제 충전 기록이 아니다: 저장할 때 서버가 직접
``recommend_service.compute_recommendation``으로 다시 계산해서 조건(request)과
결과(result)를 함께 저장하고, 조회할 때는 저장된 JSON을 그대로 돌려준다
(요금이 바뀌어도 재계산하지 않는다).
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session as DbSession

from ...domain.pricing import KST
from ...infra.db import get_session
from ...infra.models import SavedPlan, User
from ..auth_deps import current_user
from ..deps import get_tariff
from ..recommend_service import compute_recommendation
from ..schemas import PlanSummary, RecommendRequest, SavedPlanOut, SavedPlanPage

router = APIRouter(prefix="/api/me", tags=["me", "plans"])


@router.get("/plans", response_model=SavedPlanPage)
def list_plans(
    limit: int = 20,
    cursor: str | None = None,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> SavedPlanPage:
    """최신순, 커서 기반 페이지네이션. ``limit`` 기본 20."""
    query = select(SavedPlan).where(SavedPlan.user_id == user.id)

    if cursor is not None:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                SavedPlan.created_at < cursor_created_at,
                and_(
                    SavedPlan.created_at == cursor_created_at,
                    SavedPlan.id < cursor_id,
                ),
            )
        )

    query = query.order_by(SavedPlan.created_at.desc(), SavedPlan.id.desc()).limit(
        limit + 1
    )
    rows = list(session.scalars(query).all())

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more else None

    return SavedPlanPage(
        items=[_to_saved_plan_out(row) for row in rows],
        next_cursor=next_cursor,
    )


@router.get("/plans/summary", response_model=PlanSummary)
def plans_summary(
    month: str,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> PlanSummary:
    """그 달에 저장한 계획의 건수와 ``savings_won`` 합계."""
    start, end = _month_bounds(month)

    rows = session.scalars(
        select(SavedPlan).where(
            SavedPlan.user_id == user.id,
            SavedPlan.created_at >= start,
            SavedPlan.created_at < end,
        )
    ).all()

    total_savings = sum(row.result["savings_won"] for row in rows)

    return PlanSummary(month=month, count=len(rows), total_savings_won=total_savings)


@router.get("/plans/{plan_id}", response_model=SavedPlanOut)
def read_plan(
    plan_id: str,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> SavedPlanOut:
    """저장 당시 결과를 그대로 돌려준다. 재계산하지 않는다."""
    row = _get_owned_plan(session, plan_id, user.id)
    return _to_saved_plan_out(row)


@router.post("/plans", response_model=SavedPlanOut, status_code=201)
def create_plan(
    payload: RecommendRequest,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> SavedPlanOut:
    """서버가 다시 계산해 조건·결과를 저장한다. 클라이언트가 보낸 결과는 쓰지 않는다."""
    tariff = get_tariff()
    result = compute_recommendation(payload, tariff=tariff)

    row = SavedPlan(
        id=str(uuid.uuid4()),
        user_id=user.id,
        request=payload.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        tariff_version=tariff.version,
        created_at=datetime.now(KST),
    )
    session.add(row)
    session.commit()

    return SavedPlanOut(
        id=row.id,
        created_at=row.created_at,
        request=payload,
        result=result,
        tariff_version=row.tariff_version,
    )


@router.delete("/plans/{plan_id}", status_code=204)
def delete_plan(
    plan_id: str,
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> None:
    row = _get_owned_plan(session, plan_id, user.id)
    session.delete(row)
    session.commit()


def _get_owned_plan(session: DbSession, plan_id: str, user_id: str) -> SavedPlan:
    """본인 소유가 아니면(존재하지 않아도, 남의 것이어도) 404 — 403은 절대 쓰지 않는다."""
    row = session.get(SavedPlan, plan_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="충전 기록을 찾을 수 없습니다.")
    return row


def _to_saved_plan_out(row: SavedPlan) -> SavedPlanOut:
    return SavedPlanOut(
        id=row.id,
        created_at=row.created_at,
        request=row.request,
        result=row.result,
        tariff_version=row.tariff_version,
    )


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """``"YYYY-MM"``을 KST 기준 [그 달 1일 00:00, 다음 달 1일 00:00) 경계로."""
    try:
        year_str, month_str = month.split("-")
        year, month_num = int(year_str), int(month_str)
        if not 1 <= month_num <= 12:
            raise ValueError(month)
        start = datetime(year, month_num, 1, tzinfo=KST)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="month는 YYYY-MM 형식이어야 합니다."
        ) from exc

    if month_num == 12:
        end = datetime(year + 1, 1, 1, tzinfo=KST)
    else:
        end = datetime(year, month_num + 1, 1, tzinfo=KST)

    return start, end


def _encode_cursor(created_at: datetime, plan_id: str) -> str:
    raw = f"{created_at.isoformat()}|{plan_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_str, plan_id = raw.rsplit("|", 1)
        created_at = datetime.fromisoformat(created_at_str)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail="cursor가 올바르지 않습니다."
        ) from exc
    return created_at, plan_id
