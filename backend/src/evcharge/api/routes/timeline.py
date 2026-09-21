from datetime import date

from fastapi import APIRouter, Query

from ...domain.calendar import season_of
from ...domain.pricing import hourly_prices
from ..deps import get_holidays, get_tariff
from ..schemas import HourPriceOut, Mode, TimelineResponse

router = APIRouter(prefix="/api", tags=["timeline"])


@router.get("/timeline", response_model=TimelineResponse)
def timeline(
    day: date = Query(description="YYYY-MM-DD. 임의 날짜 가능 (F-06 시뮬레이션)"),
    mode: Mode = "self_low",
    public_base_price: float | None = Query(default=None, gt=0),
) -> TimelineResponse:
    tariff = get_tariff()
    holidays = get_holidays()

    hours = hourly_prices(day, mode, tariff, holidays, public_base_price)

    return TimelineResponse(
        day=day,
        mode=mode,
        season=season_of(day, tariff),
        is_holiday=holidays.is_holiday(day),
        hours=[HourPriceOut(**vars(hour)) for hour in hours],
    )
