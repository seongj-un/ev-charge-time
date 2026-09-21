from fastapi import APIRouter, HTTPException

from ...domain.errors import TariffNotConfiguredError
from ...domain.planner import ChargeRequest, ChargePlan, recommend as plan_recommend
from ...domain.pricing import price_at
from ..deps import get_holidays, get_tariff
from ..schemas import ChargePlanOut, RecommendRequest, RecommendResponse

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/recommend", response_model=RecommendResponse)
def recommend(payload: RecommendRequest) -> RecommendResponse:
    if payload.vehicle_id is not None:
        # F-12 차량 연동은 인증 구현 이후. 계약만 확정해 둔다.
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    if payload.battery_kwh is None or payload.charger_kw is None:
        raise TariffNotConfiguredError(
            "battery_kwh와 charger_kw가 필요합니다. "
            "로그인 후 vehicle_id로 차량 기본값을 쓸 수 있습니다."
        )

    tariff = get_tariff()
    holidays = get_holidays()

    request = ChargeRequest(
        battery_kwh=payload.battery_kwh,
        soc_now=payload.soc_now,
        soc_target=payload.soc_target,
        charger_kw=payload.charger_kw,
        earliest_start=payload.earliest_start,
        deadline=payload.deadline,
        mode=payload.mode,
        public_base_price=payload.public_base_price,
        efficiency=payload.efficiency,
    )

    def price_fn(moment):
        return price_at(moment, payload.mode, tariff, holidays, payload.public_base_price)

    result = plan_recommend(request, price_fn)

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
