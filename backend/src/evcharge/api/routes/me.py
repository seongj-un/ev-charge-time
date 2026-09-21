from fastapi import APIRouter

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
def read_me():
    return not_implemented("내 정보 조회")()


@router.delete("", status_code=204)
def delete_me(payload: DeleteAccountRequest):
    """F-11 탈퇴. 차량·충전 기록·즐겨찾기가 함께 삭제된다."""
    return not_implemented("회원 탈퇴")()


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
