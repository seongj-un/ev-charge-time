from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DbSession

from ...infra.db import get_session
from ...infra.models import User
from ...infra.security import verify_password
from ..auth_deps import clear_session_cookie, current_user
from ..schemas import (
    DeleteAccountRequest,
    PlanSummary,
    SavedPlanOut,
    SavedPlanPage,
    StationOut,
    UserOut,
    VehicleIn,
    VehicleOut,
)
from ._stub import not_implemented

router = APIRouter(prefix="/api/me", tags=["me"])

# 모두 로그인 필요. 본인 데이터만 접근하며 다른 사용자 리소스 ID는 404.


@router.get("", response_model=UserOut)
def read_me(user: User = Depends(current_user)):
    return user


@router.delete("", status_code=204)
def delete_me(
    payload: DeleteAccountRequest,
    response: Response,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_session),
):
    """F-11 탈퇴. 비밀번호로 재확인한다. 차량·충전 기록·즐겨찾기·세션은 DB 쪽
    ON DELETE CASCADE로 함께 삭제된다 (infra/models.py)."""
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")

    db.delete(user)
    db.commit()
    clear_session_cookie(response)
    return Response(status_code=204)


@router.get("/plans", response_model=SavedPlanPage)
def list_plans(limit: int = 20, cursor: str | None = None):
    return not_implemented("충전 기록 목록")()


@router.get("/plans/summary", response_model=PlanSummary)
def plans_summary(month: str):
    return not_implemented("월별 절감액 합계")()


@router.get("/plans/{plan_id}", response_model=SavedPlanOut)
def read_plan(plan_id: str):
    return not_implemented("충전 기록 상세")()


@router.post("/plans", response_model=SavedPlanOut, status_code=201)
def create_plan():
    """F-13. 서버가 다시 계산해 조건·결과를 저장한다 (클라이언트 결과는 쓰지 않음)."""
    return not_implemented("충전 기록 저장")()


@router.delete("/plans/{plan_id}", status_code=204)
def delete_plan(plan_id: str):
    return not_implemented("충전 기록 삭제")()


@router.get("/favorites", response_model=list[StationOut])
def list_favorites():
    return not_implemented("즐겨찾는 충전소 목록")()


@router.put("/favorites/{station_id}", status_code=204)
def add_favorite(station_id: str):
    return not_implemented("즐겨찾기 추가")()


@router.delete("/favorites/{station_id}", status_code=204)
def remove_favorite(station_id: str):
    return not_implemented("즐겨찾기 해제")()
