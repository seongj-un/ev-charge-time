from datetime import date

from fastapi import APIRouter, Query

from ...domain.calendar import season_of
from ...domain.pricing import hourly_prices
from ..deps import get_holidays, get_tariff
from ..schemas import MAX_CHARGER_KW, MAX_PRICE_PER_KWH, HourPriceOut, Mode, TimelineResponse

router = APIRouter(prefix="/api", tags=["timeline"])


@router.get("/timeline", response_model=TimelineResponse)
def timeline(
    day: date = Query(description="YYYY-MM-DD. 임의 날짜 가능 (F-06 시뮬레이션)"),
    mode: Mode = "self_low",
    public_base_price: float | None = Query(
        default=None, gt=0, le=MAX_PRICE_PER_KWH, allow_inf_nan=False
    ),
    charger_kw: float | None = Query(
        default=None,
        gt=0,
        le=MAX_CHARGER_KW,
        allow_inf_nan=False,
        description=(
            "공공 충전(public_fast)의 충전기 출력(kW). 기후에너지환경부 출력별 단가를 고른다"
        ),
    ),
) -> TimelineResponse:
    tariff = get_tariff()
    holidays = get_holidays()

    hours = hourly_prices(day, mode, tariff, holidays, public_base_price, charger_kw)

    return TimelineResponse(
        day=day,
        mode=mode,
        season=season_of(day, tariff),
        is_holiday=holidays.is_holiday(day),
        hours=[HourPriceOut(**vars(hour)) for hour in hours],
    )
