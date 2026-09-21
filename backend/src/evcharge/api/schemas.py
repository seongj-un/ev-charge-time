from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["self_low", "self_high", "public_fast"]
Band = Literal["light", "middle", "peak"]
Season = Literal["summer", "spring_fall", "winter"]


class HealthResponse(BaseModel):
    status: str
    unverified_tariff_items: list[str]


class HourPriceOut(BaseModel):
    hour: int
    band: Band
    discounted: bool
    price_per_kwh: float


class TimelineResponse(BaseModel):
    day: date
    mode: Mode
    season: Season
    is_holiday: bool
    hours: list[HourPriceOut]


class RecommendRequest(BaseModel):
    battery_kwh: float | None = Field(default=None, gt=0)
    soc_now: float = Field(ge=0, lt=100)
    soc_target: float = Field(gt=0, le=100)
    charger_kw: float | None = Field(default=None, gt=0)
    earliest_start: datetime
    deadline: datetime
    mode: Mode = "self_low"
    public_base_price: float | None = Field(default=None, gt=0)
    efficiency: float = Field(default=1.0, gt=0, le=1)
    vehicle_id: str | None = None


class ChargePlanOut(BaseModel):
    start: datetime
    end: datetime
    energy_kwh: float
    cost_won: int
    discounted_kwh: float


class RecommendResponse(BaseModel):
    best: ChargePlanOut
    baseline_now: ChargePlanOut
    savings_won: int
    candidates_checked: int
    assumptions: list[str]
    unverified_tariff_items: list[str]
