from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol

import yaml

from .errors import TariffConfigError
from .tariff import Tariff

Season = Literal["summer", "spring_fall", "winter"]
Band = Literal["light", "middle", "peak"]
DayType = Literal["weekday", "saturday", "sunday_holiday"]


class HolidayProvider(Protocol):
    """공휴일 판정. 지금은 YAML, 나중에 공공데이터포털 특일 정보 API."""

    def is_holiday(self, day: date) -> bool: ...


@dataclass(frozen=True)
class YamlHolidayProvider:
    days: frozenset[date]

    @classmethod
    def load(cls, path: Path) -> YamlHolidayProvider:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise TariffConfigError(f"공휴일 설정 파일이 없습니다: {path}") from exc

        entries = (raw or {}).get("holidays") or {}
        return cls(days=frozenset(_as_date(key) for key in entries))

    def is_holiday(self, day: date) -> bool:
        return day in self.days


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def season_of(day: date, tariff: Tariff) -> Season:
    seasons: dict[str, list[int]] = tariff.get("seasons")
    for name, months in seasons.items():
        if day.month in months:
            return name  # type: ignore[return-value]
    raise TariffConfigError(f"{day.month}월이 어느 계절에도 속하지 않습니다.")


def day_type_of(day: date, holidays: HolidayProvider) -> DayType:
    """공휴일이 요일보다 우선한다 — 토요일인 공휴일은 sunday_holiday다."""
    if day.weekday() == 6 or holidays.is_holiday(day):
        return "sunday_holiday"
    if day.weekday() == 5:
        return "saturday"
    return "weekday"


def band_at(moment: datetime, tariff: Tariff, holidays: HolidayProvider) -> Band:
    """기능 명세서 F-02의 판정 순서를 그대로 따른다."""
    day = moment.date()
    day_type = day_type_of(day, holidays)

    # 1. 일요일·공휴일 → 하루 전체 경부하
    if day_type == "sunday_holiday":
        return "light"

    # 2. 평일 시간대 표
    band = _weekday_band(moment.hour, season_of(day, tariff), tariff)

    # 3. 토요일 → 최대부하만 중간부하로 강등
    if day_type == "saturday" and band == "peak":
        return "middle"
    return band


def _weekday_band(hour: int, season: Season, tariff: Tariff) -> Band:
    table: dict[str, dict[str, list[list[int]]]] = tariff.get("time_bands")
    for band, ranges in table[season].items():
        if any(start <= hour < end for start, end in ranges):
            return band  # type: ignore[return-value]
    raise TariffConfigError(f"{season} {hour}시가 어느 부하구간에도 속하지 않습니다.")


def is_discount_hour(
    moment: datetime, tariff: Tariff, holidays: HolidayProvider
) -> bool:
    """봄·가을 토·일·공휴일 11–14시 주말 할인 (F-02).

    자가소비용과 공공 급속이 같은 창을 쓰고 할인 방식만 다르므로
    창 판정은 여기 한 곳에 둔다.
    """
    rule = tariff.get("weekend_discount_self")
    day = moment.date()

    if day.year > rule["until_year"]:
        return False
    if season_of(day, tariff) not in rule["seasons"]:
        return False
    if day_type_of(day, holidays) == "weekday":
        return False

    start, end = rule["hours"]
    return start <= moment.hour < end
