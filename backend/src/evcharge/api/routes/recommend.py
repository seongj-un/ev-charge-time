from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from ...domain.errors import TariffNotConfiguredError
from ...domain.planner import ChargeRequest, ChargePlan, recommend as plan_recommend
from ...domain.pricing import price_at
from ...infra.db import get_session
from ...infra.models import Vehicle
from ..auth_deps import current_user
from ..deps import get_holidays, get_tariff
from ..schemas import ChargePlanOut, RecommendRequest, RecommendResponse

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
def recommend(
    payload: RecommendRequest,
    request: Request,
    session: DbSession = Depends(get_session),
) -> RecommendResponse:
    battery_kwh = payload.battery_kwh
    charger_kw = payload.charger_kw
    mode = payload.mode

    if payload.vehicle_id is not None:
        # F-12 차량 연동: 로그인 필요, 본인 차량이 아니면 404.
        # 요청에 명시된 값(battery_kwh/charger_kw/mode)이 차량 기본값보다 우선한다.
        user = current_user(request, session)
        vehicle = session.get(Vehicle, payload.vehicle_id)
        if vehicle is None or vehicle.user_id != user.id:
            raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다.")

        if battery_kwh is None:
            battery_kwh = vehicle.battery_kwh
        if charger_kw is None:
            charger_kw = vehicle.charger_kw
        if "mode" not in payload.model_fields_set:
            mode = vehicle.mode

    if battery_kwh is None or charger_kw is None:
        raise TariffNotConfiguredError(
            "battery_kwh와 charger_kw가 필요합니다. "
            "로그인 후 vehicle_id로 차량 기본값을 쓸 수 있습니다."
        )

    tariff = get_tariff()
    holidays = get_holidays()

    domain_request = ChargeRequest(
        battery_kwh=battery_kwh,
        soc_now=payload.soc_now,
        soc_target=payload.soc_target,
        charger_kw=charger_kw,
        earliest_start=payload.earliest_start,
        deadline=payload.deadline,
        mode=mode,
        public_base_price=payload.public_base_price,
        efficiency=payload.efficiency,
    )

    def price_fn(moment):
        return price_at(moment, mode, tariff, holidays, payload.public_base_price)

    result = plan_recommend(domain_request, price_fn)

    return RecommendResponse(
        best=_to_out(result.best),
        baseline_now=_to_out(result.baseline_now),
        savings_won=result.savings_won,
        candidates_checked=result.candidates_checked,
        assumptions=result.assumptions,
        unverified_tariff_items=tariff.unverified_items(),
    )


def _to_out(plan: ChargePlan) -> ChargePlanOut:
    return ChargePlanOut(**vars(plan))
