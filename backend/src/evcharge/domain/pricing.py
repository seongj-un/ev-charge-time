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
from .errors import InvalidPriceError, TariffNotConfiguredError
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
        # 이 문장은 **사용자 화면에 그대로 뜬다** (422의 detail). 그래서 파일
        # 경로나 설정 키를 적지 않는다 — 읽는 사람이 고칠 수 없는 것을 시키는
        # 안내는 안내가 아니다. 공공 급속은 충전사업자가 단가를 각자 정해서
        # 하나의 공식 값이 없고(그래서 이 항목이 unverified다), 사용자가 할 수
        # 있는 일은 충전기에 적힌 단가를 넣거나 자가 충전으로 바꾸는 것뿐이다.
        raise TariffNotConfiguredError(
            "공공 급속은 충전사업자마다 단가가 달라서 단가를 알려주셔야 계산할 수 "
            "있어요. 충전기에 적힌 요금(원/kWh)을 입력하거나, 자가 충전기로 "
            "바꿔서 다시 시도해 주세요."
        )

    if not discounted:
        return float(base)

    cuts = tariff.get("public_fast.weekend_discount")
    key = "saturday" if day_type_of(day, holidays) == "saturday" else "sunday_holiday"
    cut = cuts[key]
    if base <= cut:
        # 정액 할인이라 기준단가가 할인액 이하면 0원 이하가 된다. 0으로 깎아 주면
        # "공짜 충전"이라는 거짓 답이 되므로 입력을 다시 확인하게 한다. 이 문장도
        # 화면에 그대로 뜬다 (위 TariffNotConfiguredError와 같은 규칙).
        raise InvalidPriceError(
            f"입력한 공공 급속 단가({base:g}원/kWh)가 주말 할인액({cut:g}원/kWh)보다 "
            "작거나 같아서 계산할 수 없어요. 충전기에 적힌 단가를 다시 확인해 주세요."
        )
    return float(base) - cut


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
