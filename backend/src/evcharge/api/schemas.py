from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    EmailStr,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

from ..domain.pricing import KST

Mode = Literal["self_low", "self_high", "public_fast"]
Band = Literal["light", "middle", "peak"]
Season = Literal["summer", "spring_fall", "winter"]


def _to_kst_isoformat(value: datetime) -> str:
    """DB/도메인에서 어떤 tzinfo로 오든, 응답 시각은 항상 +09:00으로 (API 명세서 1장)."""
    return value.astimezone(KST).isoformat()


# A-2: KST 직렬화 공용 처리. datetime 필드를 가진 응답 스키마마다 개별
# field_serializer를 따로 붙이던 것(UserOut.created_at, SavedPlanOut.created_at이
# 서로 모르는 채 같은 버그를 두 번 고쳤다)을 타입 별칭 하나로 대체한다.
# 필드 타입을 KstDatetime으로 선언하기만 하면 자동으로 +09:00이 보장되고,
# `KstDatetime | None`으로도 그대로 조합된다 (None은 이 직렬화기를 타지 않고
# 그대로 null로 나간다).
KstDatetime = Annotated[datetime, PlainSerializer(_to_kst_isoformat, return_type=str)]


def _normalize_email(value: str) -> str:
    """앞뒤 공백을 지우고 소문자로 통일한다.

    이메일 로컬파트는 RFC상 대소문자를 구분할 수 있지만, 이 서비스는
    "같은 사람이 두 번 가입되는" 문제를 막는 게 우선이라 통째로 소문자로
    다룬다(I-3). 가입(중복 확인·저장)과 로그인(조회) 양쪽이 이 타입을 함께
    써야 한다 — 한쪽만 정규화하면 기존 계정에 로그인이 안 된다.
    """
    return value.strip().lower()


# I-3: 이메일 형식 검증(F-11) + 소문자 정규화를 한 타입으로 묶는다.
# BeforeValidator가 EmailStr 검증보다 먼저 돌아 "정규화 → 형식 검증" 순서를
# 보장한다 — 거꾸로 하면 "Mixed@Example.COM "처럼 정규화 후에야 유효해지는
# 입력을 정규화 전 형식으로 먼저 튕겨낼 수 있다. max_length=320은
# infra/models.py의 users.email 컬럼(varchar(320))과 맞춘다(I-2).
NormalizedEmail = Annotated[
    EmailStr, BeforeValidator(_normalize_email), Field(max_length=320)
]


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
    # 도메인이 이미 KST aware datetime을 넘기므로 astimezone(KST)는 사실상
    # no-op이지만, 공용 KstDatetime을 그대로 써서 "응답의 datetime은 항상
    # +09:00" 규칙을 여기서도 따로 기억하지 않게 한다.
    start: KstDatetime
    end: KstDatetime
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


# ── 아래는 아직 구현하지 않은 엔드포인트의 계약 (스텁) ────────────────────


class SignupRequest(BaseModel):
    # NormalizedEmail이 형식 검증(EmailStr) + 소문자 정규화 + 길이 제한을
    # 한 번에 한다(I-3, I-2). nickname의 max_length는 infra/models.py의
    # users.nickname(varchar(50))과 맞춘다(I-2) — 여기서 막지 않으면 길이
    # 초과 입력이 그대로 DB까지 내려가 DataError(→ errors.py의 2차 안전망)가
    # 되는데, 그건 500을 422로 바꿔줄 뿐 진짜 1차 방어선은 아니다.
    email: NormalizedEmail
    password: str = Field(min_length=8)
    nickname: str | None = Field(default=None, max_length=50)


class LoginRequest(BaseModel):
    # 가입 때와 같은 정규화를 거쳐야 한다(I-3) — 한쪽만 정규화하면
    # "Mixed@Example.COM"으로 가입한 사람이 "mixed@example.com"으로 로그인할
    # 때 다른 문자열로 조회되어 실패한다.
    email: NormalizedEmail
    password: str


class DeleteAccountRequest(BaseModel):
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    nickname: str | None = None
    created_at: KstDatetime | None = None


class VehicleIn(BaseModel):
    # vehicles.name은 varchar(100)(I-2) — 컬럼과 어긋나지 않게 맞춘다.
    name: str = Field(max_length=100)
    battery_kwh: float = Field(gt=0)
    charger_kw: float = Field(gt=0)
    mode: Mode = "self_low"
    is_default: bool = False


class VehicleOut(VehicleIn):
    id: str


class VehicleUpdate(BaseModel):
    """PATCH 전용(C-2): 보낸 필드만 반영하는 부분 갱신.

    ``VehicleIn``을 그대로 재사용하면 ``is_default``·``mode``에 기본값이 있어서,
    예를 들어 이름만 바꾸려고 ``is_default``를 빼고 보내면 그 기본값(False)이
    실려서 기존 기본 차량이 조용히 해제됐다. 전 필드를 optional로 두고
    라우터가 ``exclude_unset=True``로 실제로 실린 필드만 골라 반영한다.
    """

    name: str | None = Field(default=None, max_length=100)
    battery_kwh: float | None = Field(default=None, gt=0)
    charger_kw: float | None = Field(default=None, gt=0)
    mode: Mode | None = None
    is_default: bool | None = None


class ChargerOut(BaseModel):
    charger_id: str
    type: str
    capacity_kw: float
    status: str
    status_updated_at: KstDatetime | None = None


class StationBase(BaseModel):
    """F-07(주변 충전소)과 F-14(즐겨찾기 목록)가 실제로 공유하는 것만 (C-1)."""

    station_id: str
    is_favorite: bool | None = None


class StationOut(StationBase):
    """F-07 주변 충전소 조회 응답. 캐시(charger_cache)가 항상 채워져 있는
    경로라 이 필드들은 전부 필수다 — F-14가 캐시 미적중을 표현하려고 예전에
    전부 optional로 완화했던 것을 원래 계약으로 되돌린다(C-1)."""

    name: str
    address: str
    lat: float
    lng: float
    distance_m: int
    operator: str
    available_hours: str
    chargers: list[ChargerOut] = Field(default_factory=list)


class FavoriteStationOut(StationBase):
    """F-14 즐겨찾기 목록 응답. charger_cache에 아직 없는 station_id도
    즐겨찾기 자체는 station_id만으로 유효하게 성립하므로, 캐시 유래 필드는
    전부 optional이다 — 캐시 미적중이면 빈 문자열/0이 아니라 None(JSON null)이
    나간다. F-07이 구현되어 캐시가 채워지면 값이 실린다(C-1)."""

    name: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    distance_m: int | None = None
    operator: str | None = None
    available_hours: str | None = None
    # []가 아니라 None이다 — []는 "충전기가 0대인 충전소",
    # None은 "아직 캐시에서 못 불러왔다"로 프론트가 다르게 표시한다.
    chargers: list[ChargerOut] | None = None


class SavedPlanOut(BaseModel):
    id: str
    created_at: KstDatetime
    request: RecommendRequest
    result: RecommendResponse
    tariff_version: str
    # 저장 당시 차량 이름 스냅샷(3번 수정). 직접 입력이면 null — 빈 문자열이
    # 아니다. 프론트가 ``vehicle_name ?? 조건폴백``으로 분기한다.
    vehicle_name: str | None = None
    # 충전 시작 시각(= result.best.start, 4번 수정). 최상위에 올려 두면
    # 프론트가 result를 파고들지 않고 목록의 날짜를 표시할 수 있다.
    # 월 필터와 목록 정렬의 기준이기도 하다.
    charge_start: KstDatetime


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
