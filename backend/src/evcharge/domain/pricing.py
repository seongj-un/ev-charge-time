from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from .calendar import (
    Band,
    HolidayProvider,
    band_at,
    day_type_of,
    is_discount_hour,
    season_of,
)
from .errors import TariffNotConfiguredError
from .tariff import Tariff

KST = ZoneInfo("Asia/Seoul")

Mode = Literal["self_low", "self_high", "public_fast"]
SELF_MODES: frozenset[str] = frozenset({"self_low", "self_high"})


@dataclass(frozen=True)
class PriceBreakdown:
    price_per_kwh: float
    band: Band
    discounted: bool


@dataclass(frozen=True)
class HourPrice:
    hour: int
    band: Band
    discounted: bool
    price_per_kwh: float


def price_at(
    moment: datetime,
    mode: Mode,
    tariff: Tariff,
    holidays: HolidayProvider,
    public_base_price: float | None = None,
) -> PriceBreakdown:
    band = band_at(moment, tariff, holidays)
    discounted = is_discount_hour(moment, tariff, holidays)

    if mode in SELF_MODES:
        price = _self_price(moment.date(), band, discounted, mode, tariff)
    else:
        price = _public_fast_price(moment.date(), discounted, tariff, holidays, public_base_price)

    return PriceBreakdown(price_per_kwh=round(price, 1), band=band, discounted=discounted)


def _self_price(
    day: date, band: Band, discounted: bool, mode: Mode, tariff: Tariff
) -> float:
    """(전력량요금 × 할인배수 + 기후환경 + 연료비조정) × (1 + 부가세율 + 기금율).

    기본요금(원/kW·월)은 명세 F-03 가정대로 제외한다.
    """
    energy = tariff.get(f"energy_charge.{mode}")[season_of(day, tariff)][band]
    multiplier = tariff.get("weekend_discount_self")["multiplier"] if discounted else 1.0

    subtotal = (
        energy * multiplier
        + tariff.get("adders.climate_env_per_kwh")
        + tariff.get("adders.fuel_adjustment_per_kwh")
    )
    return subtotal * (1 + tariff.get("vat_rate") + tariff.get("power_fund_rate"))


def _public_fast_price(
    day: date,
    discounted: bool,
    tariff: Tariff,
    holidays: HolidayProvider,
    public_base_price: float | None,
) -> float:
    base = public_base_price
    if base is None:
        base = tariff.get_optional("public_fast.base_price_per_kwh") or None
    if not base:
        raise TariffNotConfiguredError(
            "공공 급속 단가가 없습니다. public_base_price를 보내거나 "
            "config/tariff.yaml의 public_fast.base_price_per_kwh를 채우세요."
        )

    if not discounted:
        return float(base)

    cuts = tariff.get("public_fast.weekend_discount")
    key = "saturday" if day_type_of(day, holidays) == "saturday" else "sunday_holiday"
    return float(base) - cuts[key]


def hourly_prices(
    day: date,
    mode: Mode,
    tariff: Tariff,
    holidays: HolidayProvider,
    public_base_price: float | None = None,
) -> list[HourPrice]:
    prices = []
    for hour in range(24):
        moment = datetime.combine(day, time(hour), tzinfo=KST)
        breakdown = price_at(moment, mode, tariff, holidays, public_base_price)
        prices.append(
            HourPrice(
                hour=hour,
                band=breakdown.band,
                discounted=breakdown.discounted,
                price_per_kwh=breakdown.price_per_kwh,
            )
        )
    return prices
