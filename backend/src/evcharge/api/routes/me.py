from fastapi import APIRouter

from ..schemas import (
    DeleteAccountRequest,
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


@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles():
    return not_implemented("내 차량 목록")()


@router.post("/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(payload: VehicleIn):
    """F-12. is_default: true로 등록하면 기존 기본 차량은 자동 해제."""
    return not_implemented("차량 등록")()


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(vehicle_id: str, payload: VehicleIn):
    return not_implemented("차량 수정")()


@router.delete("/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: str):
    return not_implemented("차량 삭제")()


@router.get("/favorites", response_model=list[StationOut])
def list_favorites():
    return not_implemented("즐겨찾는 충전소 목록")()


@router.put("/favorites/{station_id}", status_code=204)
def add_favorite(station_id: str):
    return not_implemented("즐겨찾기 추가")()


@router.delete("/favorites/{station_id}", status_code=204)
def remove_favorite(station_id: str):
    return not_implemented("즐겨찾기 해제")()
