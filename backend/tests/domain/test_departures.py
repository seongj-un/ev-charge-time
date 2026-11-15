"""``domain/departures.py``: 평소 출발 시각 제안 규칙 (BE-8)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from evcharge.domain.departures import DepartureRecord, day_type_of, suggest, window
from evcharge.domain.errors import HolidayDataMissingError
from evcharge.domain.pricing import KST


class Holidays:
    def __init__(self, days=(), years=(2026, 2027)):
        self.days = set(days)
        self.years = set(years)

    def is_holiday(self, day: date) -> bool:
        if day.year not in self.years:
            raise HolidayDataMissingError(f"{day.year}년 공휴일 정보가 없습니다")
        return day in self.days


HOLIDAYS = Holidays(days={date(2026, 11, 18)})  # 수요일을 공휴일로
TARGET = date(2026, 11, 20)  # 금요일


def at(day: date, hhmm: str, source="observed") -> DepartureRecord:
    hour, minute = map(int, hhmm.split(":"))
    return DepartureRecord(datetime(day.year, day.month, day.day, hour, minute, tzinfo=KST), source)


def weekdays_before(target: date, count: int) -> list[date]:
    """target 전의 평일(공휴일 제외)을 가까운 날부터."""
    days, day = [], target
    while len(days) < count:
        day -= timedelta(days=1)
        if day.weekday() < 5 and day not in HOLIDAYS.days:
            days.append(day)
    return days


def test_day_types():
    assert day_type_of(date(2026, 11, 20), HOLIDAYS) == "weekday"
    assert day_type_of(date(2026, 11, 21), HOLIDAYS) == "weekend_holiday"  # 토
    assert day_type_of(date(2026, 11, 22), HOLIDAYS) == "weekend_holiday"  # 일
    assert day_type_of(date(2026, 11, 18), HOLIDAYS) == "weekend_holiday"  # 공휴일
    with pytest.raises(HolidayDataMissingError):
        day_type_of(date(2028, 1, 3), HOLIDAYS)


def test_fewer_than_three_records_give_no_suggestion():
    records = [at(day, "07:30") for day in weekdays_before(TARGET, 2)]

    result = suggest(records, TARGET, HOLIDAYS)

    assert (result.depart_at, result.confidence, result.basis_count) == (None, None, 2)
    assert result.day_type == "weekday"


def test_median_rounded_to_ten_minutes_with_high_confidence():
    times = ["07:28", "07:31", "07:33", "07:40", "07:22"]
    records = [at(day, t) for day, t in zip(weekdays_before(TARGET, 5), times, strict=True)]

    result = suggest(records, TARGET, HOLIDAYS)

    # 중앙값 07:31 → 07:30, 절대편차 중앙값 3분
    assert result.depart_at == datetime(2026, 11, 20, 7, 30, tzinfo=KST)
    assert (result.confidence, result.basis_count) == ("high", 5)


@pytest.mark.parametrize(
    ("times", "expected"),
    [
        (["07:25", "07:25", "07:25"], (7, 30)),  # 5분은 올림
        (["07:24", "07:24", "07:24"], (7, 20)),
        (["07:10", "07:20", "07:30", "07:40"], (7, 30)),  # 짝수: 가운데 둘의 평균 07:25 → 07:30
    ],
)
def test_rounding(times, expected):
    days = weekdays_before(TARGET, len(times))
    records = [at(day, t) for day, t in zip(days, times, strict=True)]

    result = suggest(records, TARGET, HOLIDAYS)

    assert (result.depart_at.hour, result.depart_at.minute) == expected
    assert result.confidence == "low"  # 5건 미만


def test_spread_over_twenty_minutes_is_low():
    times = ["07:00", "07:10", "07:30", "07:55", "08:00"]
    records = [at(day, t) for day, t in zip(weekdays_before(TARGET, 5), times, strict=True)]

    result = suggest(records, TARGET, HOLIDAYS)

    # 중앙값 07:30, 편차 30·20·0·25·30 → 중앙값 25분
    assert (result.depart_at.hour, result.depart_at.minute, result.confidence) == (7, 30, "low")


def test_spread_of_exactly_twenty_minutes_is_high():
    times = ["07:10", "07:10", "07:30", "07:50", "07:50"]
    records = [at(day, t) for day, t in zip(weekdays_before(TARGET, 5), times, strict=True)]

    assert suggest(records, TARGET, HOLIDAYS).confidence == "high"


def test_only_the_same_day_type_counts():
    weekend = [at(date(2026, 11, d), "10:00") for d in (14, 15, 18)]  # 토, 일, 공휴일(수)
    weekday = [at(day, "07:30") for day in weekdays_before(TARGET, 3)]

    on_weekday = suggest(weekend + weekday, TARGET, HOLIDAYS)
    on_saturday = suggest(weekend + weekday, date(2026, 11, 21), HOLIDAYS)

    assert (on_weekday.depart_at.hour, on_weekday.basis_count) == (7, 3)
    assert on_saturday.day_type == "weekend_holiday"
    assert (on_saturday.depart_at.hour, on_saturday.basis_count) == (10, 3)


def test_observed_wins_when_there_are_three():
    days = weekdays_before(TARGET, 6)
    observed = [at(day, "07:30") for day in days[:3]]
    stated = [at(day, "09:00", "stated") for day in days[3:]]

    result = suggest(observed + stated, TARGET, HOLIDAYS)

    assert (result.depart_at.hour, result.depart_at.minute, result.basis_count) == (7, 30, 3)


def test_stated_fills_in_when_observed_are_few():
    days = weekdays_before(TARGET, 4)
    records = [at(days[0], "07:30"), *(at(day, "08:00", "stated") for day in days[1:])]

    result = suggest(records, TARGET, HOLIDAYS)

    assert (result.depart_at.hour, result.basis_count) == (8, 4)


def test_window_is_the_28_days_before_the_target():
    start, end = window(TARGET)
    inside = [at(start.date(), "07:30"), at(TARGET - timedelta(days=1), "07:30")]
    inside.append(at(date(2026, 11, 2), "07:30"))
    outside = [
        at(start.date() - timedelta(days=1), "07:30"),  # 29일 전
        at(TARGET, "06:00"),  # 그날 당일
    ]

    result = suggest(inside + outside, TARGET, HOLIDAYS)

    assert end == datetime(2026, 11, 20, tzinfo=KST)
    assert start == datetime(2026, 10, 23, tzinfo=KST)
    assert result.basis_count == 3


def test_records_from_years_without_holiday_data_use_weekdays_only():
    target = date(2026, 1, 9)  # 금
    holidays = Holidays(years=(2026,))
    records = [at(date(2025, 12, d), "07:30") for d in (29, 30, 31)]  # 월화수

    assert suggest(records, target, holidays).basis_count == 3


def test_target_without_holiday_data_raises():
    with pytest.raises(HolidayDataMissingError):
        suggest([], date(2028, 1, 3), HOLIDAYS)


@pytest.mark.parametrize(
    "times",
    [
        ["23:56"] * 5,  # 반올림하면 다음 날 00:00
        ["22:00"] * 5,
        ["21:55", "21:56", "21:57"],  # 반올림 22:00
        ["23:50", "00:10", "23:55", "00:05", "23:58"],  # 자정을 넘나드는 출발
    ],
)
def test_late_night_departures_give_no_suggestion(times):
    days = weekdays_before(TARGET, len(times))
    records = [at(day, t) for day, t in zip(days, times, strict=True)]

    result = suggest(records, TARGET, HOLIDAYS)

    assert (result.depart_at, result.confidence, result.basis_count) == (None, None, len(times))


def test_the_latest_suggestion_stays_on_the_target_day():
    records = [at(day, "21:54") for day in weekdays_before(TARGET, 5)]

    result = suggest(records, TARGET, HOLIDAYS)

    assert result.depart_at == datetime(2026, 11, 20, 21, 50, tzinfo=KST)
    assert result.depart_at.date() == TARGET
