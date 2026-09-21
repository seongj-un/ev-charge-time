from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from evcharge.domain.calendar import YamlHolidayProvider
from evcharge.domain.errors import TariffNotConfiguredError
from evcharge.domain.pricing import hourly_prices, price_at
from evcharge.domain.tariff import Tariff
from evcharge.settings import get_settings

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture(scope="module")
def tariff() -> Tariff:
    return Tariff.load(get_settings().tariff_path)


@pytest.fixture(scope="module")
def holidays() -> YamlHolidayProvider:
    return YamlHolidayProvider.load(get_settings().holidays_path)


def at(y, m, d, hour):
    return datetime(y, m, d, hour, tzinfo=KST)


def test_bands_are_ordered_cheapest_to_dearest(tariff, holidays):
    """경부하 < 중간부하 < 최대부하.

    절대값이 아니라 순서를 검증한다. 잠정치를 한전 공식 요금표로
    갈아끼워도 이 테스트는 그대로 살아있고 회귀를 잡는다.
    """
    weekday = date(2026, 10, 16)  # 금요일, 봄·가을
    light = price_at(at(2026, 10, 16, 2), "self_low", tariff, holidays)
    middle = price_at(at(2026, 10, 16, 9), "self_low", tariff, holidays)
    peak = price_at(at(2026, 10, 16, 16), "self_low", tariff, holidays)

    assert (light.band, middle.band, peak.band) == ("light", "middle", "peak")
    assert light.price_per_kwh < middle.price_per_kwh < peak.price_per_kwh
    assert weekday.weekday() == 4


def test_weekend_discount_lowers_price_within_same_band(tariff, holidays):
    """봄·가을 토요일 12시는 같은 날 10시와 같은 중간부하지만 더 싸다."""
    discounted = price_at(at(2026, 10, 17, 12), "self_low", tariff, holidays)
    normal = price_at(at(2026, 10, 17, 10), "self_low", tariff, holidays)

    assert discounted.band == normal.band == "middle"
    assert discounted.discounted is True
    assert normal.discounted is False
    assert discounted.price_per_kwh < normal.price_per_kwh


def test_public_fast_subtracts_flat_discount(tariff, holidays):
    saturday = price_at(
        at(2026, 10, 17, 12), "public_fast", tariff, holidays, public_base_price=350.0
    )
    sunday = price_at(
        at(2026, 10, 18, 12), "public_fast", tariff, holidays, public_base_price=350.0
    )
    weekday = price_at(
        at(2026, 10, 16, 12), "public_fast", tariff, holidays, public_base_price=350.0
    )

    assert saturday.price_per_kwh == pytest.approx(301.4)
    assert sunday.price_per_kwh == pytest.approx(307.3)
    assert weekday.price_per_kwh == pytest.approx(350.0)
    assert weekday.discounted is False


def test_public_fast_without_a_price_is_rejected(tariff, holidays):
    with pytest.raises(TariffNotConfiguredError):
        price_at(at(2026, 10, 16, 12), "public_fast", tariff, holidays)


def test_hourly_prices_covers_the_whole_day(tariff, holidays):
    hours = hourly_prices(date(2026, 10, 17), "self_low", tariff, holidays)

    assert len(hours) == 24
    assert [h.hour for h in hours] == list(range(24))
    assert [h.hour for h in hours if h.discounted] == [11, 12, 13]


def test_self_high_is_cheaper_than_self_low(tariff, holidays):
    low = price_at(at(2026, 10, 16, 16), "self_low", tariff, holidays)
    high = price_at(at(2026, 10, 16, 16), "self_high", tariff, holidays)

    assert high.price_per_kwh < low.price_per_kwh
