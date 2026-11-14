"""차량 앱(Pleos Connect)용 엔드포인트. 계약: docs/car-api.md.

차량 앱은 로그인 없이 쓴다. 계산 엔드포인트는 기기 토큰이 없으면 DB를 쓰지 않는다.
기기 토큰과 절감 기록은 ``car_devices``·``car_savings``(BE-5)에 있다.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session as DbSession

from ...domain.pricing import KST
from ...infra.db import get_session
from ...settings import get_settings
from ..car_devices import client_ip, consume_device_quota, issue_device
from ..car_leak_service import compute_leak_check
from ..car_plan_service import compute_car_plan
from ..car_savings import try_record
from ..deps import get_public_prices
from ..schemas import (
    CarDeviceOut,
    CarLeakCheckRequest,
    CarLeakCheckResponse,
    CarPlanRequest,
    CarPlanResponse,
)

router = APIRouter(prefix="/api/car", tags=["car"])


def now_kst() -> datetime:
    """서버 현재 시각. 테스트가 이 함수를 바꿔 시각을 고정한다."""
    return datetime.now(KST)


@router.post("/plan", response_model=CarPlanResponse)
def car_plan(payload: CarPlanRequest, request: Request) -> CarPlanResponse:
    """가장 싼 충전 구간, 차량 예약 충전에 넣을 값, TTS로 읽을 문장을 돌려준다.

    기기 토큰이 있고 아끼는 돈이 있으면 대기 절감 기록을 만들고 ``saving_id``를 붙인다.
    """
    result = compute_car_plan(payload, now_kst())
    if result.plan is not None and result.savings_won:
        saving_id = try_record(
            request,
            cause="time",
            savings_won=result.savings_won,
            energy_kwh=result.plan.energy_kwh,
            source="plan",
        )
        result = result.model_copy(update={"saving_id": saving_id})
    return result


@router.post("/leak-check", response_model=CarLeakCheckResponse)
def car_leak_check(payload: CarLeakCheckRequest, request: Request) -> CarLeakCheckResponse:
    """충전 중에 돈이 새고 있는지(비싼 시간대·비싼 결제 방식) 알려 준다.

    기기 토큰이 있고 ``leaking=true``면 대기 절감 기록을 만들고 ``saving_id``를 붙인다.
    """
    result = compute_leak_check(
        payload,
        now_kst(),
        min_won=get_settings().car_leak_min_won,
        load_prices=get_public_prices,
    )
    if result.leaking and result.cause is not None:
        saving_id = try_record(
            request,
            cause=result.cause,
            savings_won=result.leak_won,
            energy_kwh=result.energy_kwh,
            source="leak_check",
        )
        result = result.model_copy(update={"saving_id": saving_id})
    return result


@router.post("/devices", response_model=CarDeviceOut, status_code=201)
def register_device(
    request: Request, response: Response, session: DbSession = Depends(get_session)
) -> CarDeviceOut:
    """기기 토큰 발급. 토큰은 이 응답에서 한 번만 보이고 서버는 해시만 저장한다."""
    consume_device_quota(session, client_ip(request), now_kst())
    device_id, token = issue_device(session)
    response.headers["Cache-Control"] = "no-store"
    return CarDeviceOut(device_id=device_id, device_token=token)
