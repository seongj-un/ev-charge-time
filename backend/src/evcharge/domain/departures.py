"""출발 시각 학습 (와트잇 BE-8): 기록에서 평소 출발 시각을 제안한다.

기록은 두 가지다.

- ``observed``: 앱이 Vehicle 기어가 P에서 벗어난 첫 시각(집 출발)을 보낸 것
- ``stated``: 운전자가 직접 말한 출발 시각(car/plan, car/leak-check, 음성 plan_charge)

제안 규칙 (명세 BE-8)

1. 제안할 날(``target``) 전 28일(``target - 28일`` ~ ``target - 1일``, KST 날짜) 기록 중
   같은 날 종류(평일 / 주말·공휴일)만 쓴다.
2. observed가 3건 이상이면 observed만, 아니면 둘 다 쓴다(실제 출발이 말한 것보다 정확하다).
3. 3건 미만이면 제안하지 않는다.
4. 하루 분(0~1439)의 중앙값을 10분 단위로 반올림한다(5분은 올림).
5. 5건 이상이고 중앙값 절대편차가 20분 이하이면 ``high``, 아니면 ``low``.

한계: 자정을 넘나드는 출발(23:50, 00:10)은 하루 분으로 보면 멀리 떨어져 중앙값이 틀린다.
아침 출발을 위한 기능이라 다루지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import floor
from statistics import median
from typing import Literal

from .calendar import HolidayProvider
from .errors import HolidayDataMissingError
from .pricing import KST

DepartureSource = Literal["observed", "stated"]
DepartureDayType = Literal["weekday", "weekend_holiday"]
Confidence = Literal["high", "low"]

WINDOW_DAYS = 28
MIN_BASIS = 3
HIGH_MIN_BASIS = 5
HIGH_MAX_SPREAD_MIN = 20
ROUND_MIN = 10
# 반올림한 중앙값이 이 시각(하루 분) 이후면 제안하지 않는다. 아침 출발용 기능이고, 하루 분의
# 중앙값은 자정을 넘나드는 출발에서 틀리며(23:50과 00:10), 23:55 이후는 반올림하면 다음 날
# 00:00이 되어 제안한 날과 시각의 날짜가 어긋난다.
LATEST_SUGGESTION_MIN = 22 * 60


@dataclass(frozen=True)
class DepartureRecord:
    departed_at: datetime
    source: DepartureSource


@dataclass(frozen=True)
class DepartureSuggestion:
    target: date
    day_type: DepartureDayType
    # 제안이 없으면 None
    depart_at: datetime | None
    confidence: Confidence | None
    basis_count: int


def day_type_of(day: date, holidays: HolidayProvider) -> DepartureDayType:
    """토·일·공휴일이면 ``weekend_holiday``. 공휴일 정보가 없는 해는 ``HolidayDataMissingError``."""
    if day.weekday() >= 5 or holidays.is_holiday(day):
        return "weekend_holiday"
    return "weekday"


def _record_day_type(day: date, holidays: HolidayProvider) -> DepartureDayType:
    """기록의 날 종류. 공휴일 정보가 없는 해의 기록은 요일로만 가른다(기록을 버리지 않는다)."""
    try:
        return day_type_of(day, holidays)
    except HolidayDataMissingError:
        return "weekend_holiday" if day.weekday() >= 5 else "weekday"


def window(target: date) -> tuple[datetime, datetime]:
    """기록을 읽을 구간 ``[target - 28일 0시, target 0시)`` (KST)."""
    end = datetime.combine(target, time(), tzinfo=KST)
    return end - timedelta(days=WINDOW_DAYS), end


def suggest(
    records: list[DepartureRecord], target: date, holidays: HolidayProvider
) -> DepartureSuggestion:
    """``target`` 날의 평소 출발 시각. ``target``의 공휴일 정보가 없으면 예외가 그대로 난다."""
    day_type = day_type_of(target, holidays)
    start, end = window(target)
    same = [
        record
        for record in records
        if start <= record.departed_at < end
        and _record_day_type(record.departed_at.astimezone(KST).date(), holidays) == day_type
    ]
    observed = [record for record in same if record.source == "observed"]
    basis = observed if len(observed) >= MIN_BASIS else same
    if len(basis) < MIN_BASIS:
        return DepartureSuggestion(target, day_type, None, None, len(basis))

    minutes = [_minute_of_day(record.departed_at) for record in basis]
    middle = median(minutes)
    spread = median(abs(minute - middle) for minute in minutes)
    rounded = floor(middle / ROUND_MIN + 0.5) * ROUND_MIN
    if rounded >= LATEST_SUGGESTION_MIN:
        return DepartureSuggestion(target, day_type, None, None, len(basis))
    confidence: Confidence = (
        "high" if len(basis) >= HIGH_MIN_BASIS and spread <= HIGH_MAX_SPREAD_MIN else "low"
    )
    depart_at = datetime.combine(target, time(), tzinfo=KST) + timedelta(minutes=rounded)
    return DepartureSuggestion(target, day_type, depart_at, confidence, len(basis))


def _minute_of_day(moment: datetime) -> int:
    local = moment.astimezone(KST)
    return local.hour * 60 + local.minute
