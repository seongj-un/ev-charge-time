"""F-13 충전 기록(저장한 추천 계획).

``routes/me.py``가 다른 엔드포인트(내 정보·차량·즐겨찾기)의 스텁을 담고 있고
다른 에이전트가 그 파일을 동시에 건드리고 있어, 저장한 계획 엔드포인트는
별도 라우터로 뺐다. ``main.py``에 나란히 등록한다.

저장한 계획은 "계획"이지 실제 충전 기록이 아니다: 저장할 때 서버가 직접
``recommend_service.compute_recommendation``으로 다시 계산해서 조건(request)과
결과(result)를 함께 저장하고, 조회할 때는 저장된 JSON을 그대로 돌려준다
(요금이 바뀌어도 재계산하지 않는다). vehicle_id로 저장했으면 그 시점 차량
이름도 ``vehicle_name``에 스냅샷으로 함께 저장한다(3번 수정) — tariff_version과
같은 이유로, 차량이 나중에 지워지거나 이름이 바뀌어도 "그때 무엇으로
계획했는지"는 남아야 한다.
"""

from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session as DbSession

from ...domain.pricing import KST
from ...infra.db import get_session
from ...infra.models import SavedPlan, User
from ..auth_deps import current_user
from ..deps import get_tariff
from ..recommend_service import compute_recommendation
from ..schemas import PlanSummary, RecommendRequest, SavedPlanOut, SavedPlanPage
from ..vehicle_resolution import resolve_vehicle_defaults

router = APIRouter(prefix="/api/me", tags=["me", "plans"])

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@router.get("/plans", response_model=SavedPlanPage)
def list_plans(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    month: str | None = Query(default=None),
    user: User = Depends(current_user),
    session: DbSession = Depends(get_session),
) -> SavedPlanPage:
    """충전 날짜 내림차순, 커서 기반 페이지네이션. ``limit`` 기본 20, 1~100 (B-1).

    하한이 없으면 ``?limit=0``(또는 음수)이 저장 기록 1건 이상인 사용자에게
    ``has_more``를 빈 슬라이스 전에 계산한 뒤 ``rows[-1]``을 해서 IndexError →
    500을 냈다(라이브 서버에서 재현됨). 상한도 함께 거는 이유는
    ``?limit=999999``가 DB를 통째로 긁어오는 것을 막기 위해서다.

    ``month``(``"YYYY-MM"``, 2번 수정)는 ``/plans/summary``가 쓰는
    ``_month_bounds``를 그대로 재사용한다 — 프론트가 이 필터 없이 커서로 받아
    직접 거르면, 그 달 기록이 아직 안 넘어온 다음 페이지에 있어 화면에서
    누락되는 문제가 생겨서 서버가 먼저 걸러야 한다. 안 주면(``None``) 기존과
    완전히 동일하게 전체를 반환한다.

    필터·정렬·커서가 모두 ``charge_start``(충전 시작 시각) 기준이다(4번 수정).
    예전에는 ``created_at``(저장 시각)이었는데, 화면이 보여주는 날짜는 충전
    날짜이므로 거르는 기준과 보이는 기준이 어긋났다 — 9월에 저장한 "10월 7일
    충전 계획"이 10월 필터에 안 잡혔고, 10월로 걸러도 순서는 저장한 순서라
    날짜 열이 뒤죽박죽 나왔다. ``created_at``은 "언제 세운 계획인지"를 위해
    응답에는 그대로 남는다.
    """
    query = select(SavedPlan).where(SavedPlan.user_id == user.id)

    if month is not None:
        start, end = _month_bounds(month)
        query = query.where(
            SavedPlan.charge_start >= start, SavedPlan.charge_start < end
        )

    if cursor is not None:
        cursor_charge_start, cursor_id = _decode_cursor(cursor)
        query = query.where(
            or_(
                SavedPlan.charge_start < cursor_charge_start,
                and_(
                    SavedPlan.charge_start == cursor_charge_start,
                    SavedPlan.id < cursor_id,
                ),
            )
        )

    query = query.order_by(SavedPlan.charge_start.desc(), SavedPlan.id.desc()).limit(
        limit + 1
    )
    rows = list(session.scalars(query).all())

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = (
        _encode_cursor(rows[-1].charge_start, rows[-1].id) if has_more else None
    )

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
    """그 달에 **충전할** 계획의 건수와 ``savings_won`` 합계.

    저장한 달이 아니라 충전하는 달 기준이다(4번 수정) — 사용자가 묻는 것은
    "10월에 얼마나 아끼나"이지 "9월에 계획을 몇 번 세웠나"가 아니다.
    ``/plans?month=``과 같은 기준이어야 목록 건수와 합계가 맞는다.
    """
    start, end = _month_bounds(month)

    rows = session.scalars(
        select(SavedPlan).where(
            SavedPlan.user_id == user.id,
            SavedPlan.charge_start >= start,
            SavedPlan.charge_start < end,
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
    """서버가 다시 계산해 조건·결과를 저장한다. 클라이언트가 보낸 결과는 쓰지 않는다.

    vehicle_id 해석은 ``/api/recommend``와 같은 ``resolve_vehicle_defaults``를
    쓴다(3번 수정) — 이 엔드포인트는 이미 로그인을 요구하므로(``current_user``
    의존성) 세션을 vehicle_id 유무로 조건부로 열 필요가 없어 1번 수정과
    부딪히지 않는다.
    """
    payload, vehicle_name = resolve_vehicle_defaults(payload, user, session)

    tariff = get_tariff()
    result = compute_recommendation(payload, tariff=tariff)

    row = SavedPlan(
        id=str(uuid.uuid4()),
        user_id=user.id,
        request=payload.model_dump(mode="json"),
        result=result.model_dump(mode="json"),
        tariff_version=tariff.version,
        vehicle_name=vehicle_name,
        charge_start=result.best.start,
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
        vehicle_name=row.vehicle_name,
        charge_start=row.charge_start,
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
        vehicle_name=row.vehicle_name,
        charge_start=row.charge_start,
    )


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """``"YYYY-MM"``을 KST 기준 [그 달 1일 00:00, 다음 달 1일 00:00) 경계로.

    (B-3) 예전에는 형식 검증이 없어 ``"26-10"``이나 ``"2026-2"``도 조용히
    받아 ``month``를 그대로 응답에 되돌려줬다. ``int()``/범위 체크만으로는
    자릿수가 다른 값을 걸러내지 못해 ``YYYY-MM`` 정규식으로 먼저 형식 자체를
    확인한다.
    """
    if not _MONTH_RE.match(month):
        raise HTTPException(
            status_code=422, detail="month는 YYYY-MM 형식이어야 합니다."
        )
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


def _encode_cursor(charge_start: datetime, plan_id: str) -> str:
    """커서는 정렬 키와 같은 쌍이어야 한다 — ``(charge_start, id)`` (4번 수정).

    id 타이브레이커가 필요한 이유: 같은 시각에 시작하는 계획이 여러 건일 수
    있고, 그때 커서가 시각만 들고 있으면 같은 시각 행들을 건너뛰거나 중복해서
    돌려준다.
    """
    raw = f"{charge_start.isoformat()}|{plan_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        charge_start_str, plan_id = raw.rsplit("|", 1)
        charge_start = datetime.fromisoformat(charge_start_str)
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail="cursor가 올바르지 않습니다."
        ) from exc
    return charge_start, plan_id
