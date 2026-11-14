"""차량 앱(Pleos Connect)용 엔드포인트. 계약: docs/car-api.md.

차량 앱은 로그인 없이 쓰고, 여기 엔드포인트는 DB를 쓰지 않는다.
"""

from datetime import datetime

from fastapi import APIRouter

from ...domain.pricing import KST
from ...settings import get_settings
from ..car_leak_service import compute_leak_check
from ..car_plan_service import compute_car_plan
from ..deps import get_public_prices
from ..schemas import CarLeakCheckRequest, CarLeakCheckResponse, CarPlanRequest, CarPlanResponse

router = APIRouter(prefix="/api/car", tags=["car"])


def now_kst() -> datetime:
    """서버 현재 시각. 테스트가 이 함수를 바꿔 시각을 고정한다."""
    return datetime.now(KST)


@router.post("/plan", response_model=CarPlanResponse)
def car_plan(payload: CarPlanRequest) -> CarPlanResponse:
    """가장 싼 충전 구간, 차량 예약 충전에 넣을 값, TTS로 읽을 문장을 돌려준다."""
    return compute_car_plan(payload, now_kst())


@router.post("/leak-check", response_model=CarLeakCheckResponse)
def car_leak_check(payload: CarLeakCheckRequest) -> CarLeakCheckResponse:
    """충전 중에 돈이 새고 있는지(비싼 시간대·비싼 결제 방식) 알려 준다."""
    return compute_leak_check(
        payload,
        now_kst(),
        min_won=get_settings().car_leak_min_won,
        prices=get_public_prices(),
    )
