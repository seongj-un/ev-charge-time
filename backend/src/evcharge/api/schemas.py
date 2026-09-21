from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from ..domain.pricing import KST

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

    @field_validator("earliest_start", "deadline")
    @classmethod
    def _normalize_to_kst(cls, value: datetime) -> datetime:
        """타임존 없는 입력은 한국 시간으로 읽고, 있는 입력은 KST로 옮긴다.

        내부 계산이 전부 KST aware라는 전제를 입구에서 세운다 (API 명세서 1장).
        """
        if value.tzinfo is None:
            return value.replace(tzinfo=KST)
        return value.astimezone(KST)

    @model_validator(mode="after")
    def _check_ranges(self) -> "RecommendRequest":
        if self.soc_target <= self.soc_now:
            raise ValueError("soc_target은 soc_now보다 커야 합니다.")
        if self.deadline <= self.earliest_start:
            raise ValueError("deadline은 earliest_start보다 뒤여야 합니다.")
        return self


class ChargePlanOut(BaseModel):
    start: datetime
    end: datetime
    energy_kwh: float
    cost_won: int
    discounted_kwh: float

    @field_serializer("start", "end")
    def _as_kst(self, value: datetime) -> str:
        """응답 시각은 항상 +09:00을 달고 나간다 (API 명세서 1장)."""
        return value.astimezone(KST).isoformat()


class RecommendResponse(BaseModel):
    best: ChargePlanOut
    baseline_now: ChargePlanOut
    savings_won: int
    candidates_checked: int
    assumptions: list[str]
    unverified_tariff_items: list[str]


# ── 아래는 아직 구현하지 않은 엔드포인트의 계약 (스텁) ────────────────────


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    nickname: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class DeleteAccountRequest(BaseModel):
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    nickname: str | None = None
    created_at: datetime | None = None


class VehicleIn(BaseModel):
    name: str
    battery_kwh: float = Field(gt=0)
    charger_kw: float = Field(gt=0)
    mode: Mode = "self_low"
    is_default: bool = False


class VehicleOut(VehicleIn):
    id: str


class ChargerOut(BaseModel):
    charger_id: str
    type: str
    capacity_kw: float
    status: str
    status_updated_at: datetime | None = None


class StationOut(BaseModel):
    station_id: str
    # F-07(주변 충전소 조회)이 채우는 캐시 파생 필드. F-14 즐겨찾기 목록은
    # charger_cache에 아직 없는 station_id도 유효하게 보여줘야 하므로
    # (즐겨찾기 자체는 station_id만으로 성립), 전부 선택 필드로 둔다 — 캐시가
    # 없으면 station_id만 채우고 나머지는 비운 채 응답한다.
    name: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    distance_m: int | None = None
    operator: str | None = None
    available_hours: str | None = None
    is_favorite: bool | None = None
    chargers: list[ChargerOut] = Field(default_factory=list)


class SavedPlanOut(BaseModel):
    id: str
    created_at: datetime
    request: RecommendRequest
    result: RecommendResponse
    tariff_version: str


class SavedPlanPage(BaseModel):
    items: list[SavedPlanOut]
    next_cursor: str | None = None


class PlanSummary(BaseModel):
    month: str
    count: int
    total_savings_won: int


class SolarHour(BaseModel):
    hour: int
    predicted_mwh: float


class SolarForecast(BaseModel):
    region: str
    day: date
    model_version: str
    hours: list[SolarHour]


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    answer: str
    recommendation: RecommendResponse | None = None
    missing_fields: list[str] = []
