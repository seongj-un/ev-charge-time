from fastapi import APIRouter, Query

from ..schemas import StationOut
from ._stub import not_implemented

router = APIRouter(prefix="/api", tags=["chargers"])


@router.get("/chargers", response_model=list[StationOut])
def list_chargers(
    lat: float = Query(description="위도. 조회에만 쓰고 저장하지 않는다"),
    lng: float = Query(description="경도. 조회에만 쓰고 저장하지 않는다"),
    radius_m: int = 2000,
    charger_type: str | None = None,
):
    """F-07 주변 충전소. 한국환경공단 API 연동 + 전 사용자 공유 캐시 예정."""
    return not_implemented("주변 충전소 조회")()
