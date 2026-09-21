from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from evcharge.domain.calendar import (
    YamlHolidayProvider,
    band_at,
    day_type_of,
    is_discount_hour,
    season_of,
)
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


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 5, 31), "spring_fall"),
        (date(2026, 6, 1), "summer"),
        (date(2026, 8, 31), "summer"),
        (date(2026, 9, 1), "spring_fall"),
        (date(2026, 10, 31), "spring_fall"),
        (date(2026, 11, 1), "winter"),
        (date(2027, 2, 28), "winter"),
        (date(2027, 3, 1), "spring_fall"),
    ],
)
def test_season_boundaries(tariff, day, expected):
    assert season_of(day, tariff) == expected


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 10, 7), "weekday"),        # 수요일
        (date(2026, 10, 10), "saturday"),      # 토요일
        (date(2026, 10, 11), "sunday_holiday"),  # 일요일
        (date(2026, 10, 3), "sunday_holiday"),   # 개천절 — 토요일이지만 공휴일 우선
    ],
)
def test_day_type(holidays, day, expected):
    assert day_type_of(day, holidays) == expected


def test_sunday_is_light_all_day(tariff, holidays):
    for hour in range(24):
        assert band_at(at(2026, 10, 11, hour), tariff, holidays) == "light"


def test_saturday_demotes_peak_to_middle(tariff, holidays):
    # 2026-10-16(금)과 2026-10-17(토)은 같은 계절, 같은 시각, 둘 다 공휴일 아님
    assert band_at(at(2026, 10, 16, 16), tariff, holidays) == "peak"
    assert band_at(at(2026, 10, 17, 16), tariff, holidays) == "middle"


def test_saturday_keeps_light_and_middle(tariff, holidays):
    assert band_at(at(2026, 10, 17, 2), tariff, holidays) == "light"
    assert band_at(at(2026, 10, 17, 9), tariff, holidays) == "middle"


def test_winter_weekday_bands(tariff, holidays):
    # 2026-12-02는 수요일
    assert band_at(at(2026, 12, 2, 10), tariff, holidays) == "peak"
    assert band_at(at(2026, 12, 2, 13), tariff, holidays) == "middle"
    assert band_at(at(2026, 12, 2, 17), tariff, holidays) == "peak"
    assert band_at(at(2026, 12, 2, 23), tariff, holidays) == "light"


@pytest.mark.parametrize(
    "moment,expected",
    [
        (at(2026, 10, 10, 11), True),   # 봄가을 토요일 11시
        (at(2026, 10, 10, 13), True),   # 13시 (14시 미만)
        (at(2026, 10, 10, 14), False),  # 14시는 제외
        (at(2026, 10, 10, 10), False),  # 11시 이전
        (at(2026, 10, 11, 12), True),   # 봄가을 일요일
        (at(2026, 7, 11, 12), False),   # 여름 토요일 — 할인 없음
        (at(2026, 10, 7, 12), False),   # 봄가을 평일 — 할인 없음
    ],
)
def test_discount_hours(tariff, holidays, moment, expected):
    assert is_discount_hour(moment, tariff, holidays) is expected


def test_holiday_on_saturday_beats_weekday_table(tariff, holidays):
    """2026-10-09 한글날은 금요일이지만 공휴일이라 종일 경부하."""
    assert band_at(at(2026, 10, 9, 16), tariff, holidays) == "light"
