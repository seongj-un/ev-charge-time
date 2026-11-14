from __future__ import annotations

from datetime import date, datetime, timedelta
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


def _normalize_email(value: object) -> object:
    """앞뒤 공백을 지우고 소문자로 통일한다.

    이메일 로컬파트는 RFC상 대소문자를 구분할 수 있지만, 이 서비스는
    "같은 사람이 두 번 가입되는" 문제를 막는 게 우선이라 통째로 소문자로
    다룬다(I-3). 가입(중복 확인·저장)과 로그인(조회) 양쪽이 이 타입을 함께
    써야 한다 — 한쪽만 정규화하면 기존 계정에 로그인이 안 된다.

    BeforeValidator라 타입 검증보다 먼저 돈다. 문자열이 아니면(null·숫자·배열)
    손대지 않고 그대로 넘겨 EmailStr이 422로 거절하게 한다 — 여기서 .strip()을
    부르면 AttributeError로 500이 난다.
    """
    if not isinstance(value, str):
        return value
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


# I-4: 탐색 구간 상한. 인증 없이 도달 가능한 POST /api/recommend가 구간에
# 상한이 없어 리뷰어 실측으로 9년 구간(스키마가 연도 9999도 그대로 받는다)
# = 12.6초/265MB/후보 315,533개를 냈다 — curl 한 줄로 워커를 수 분간 묶고
# OOM까지 갈 수 있는 DoS였다.
#
# 도메인(planner)이 아니라 여기(스키마)에 두는 이유: 이 상한은 "이 계산이
# 수학적으로 틀렸다"는 도메인 규칙이 아니라 "이 값을 HTTP로 노출하는 서비스를
# 무제한 계산으로부터 보호한다"는 API 경계의 정책이다. 도메인은 HTTP도,
# 인증 여부도, 무엇이 "정상적인 사용"인지도 모른다 — 9년 구간도 수학적으로는
# 정확히 계산해낸다(그냥 느릴 뿐). 반대로 soc_target/soc_now 순서나
# deadline/earliest_start 순서 같은, "입력 자체의 앞뒤가 맞는지"는 같은
# _check_ranges에서 이미 스키마가 보고 있다 — 도메인(ChargeRequest)은 그런
# 정합성을 스스로 검증하지 않고 받은 그대로 계산한다. 이 상한도 같은 성격의
# "입력이 서비스가 감당할 범위인지" 검사라 같은 자리에 둔다.
#
# 값(14일) 근거: 기능 명세 시나리오 A(퇴근 후 귀가 → 다음날 출근 전)와 주말
# 낮 구간이 실제 용례의 전부다 — 며칠을 넘는 "계획"은 이 서비스가 답하려는
# 질문이 아니다. 그래도 여행 중 숙소에 며칠 머무는 것 같은 정당한 장기 사용을
# 막지 않도록 넉넉히 14일로 잡았다. 리뷰어 실측 기준 90일 구간(0.35초/8,573
# 후보)에도 크게 못 미쳐 부하 걱정 없이 여유가 있다.
MAX_REQUEST_SPAN = timedelta(days=14)


# 숫자 입력의 계산 가능 범위. gt=0만으로는 "Infinity"·"NaN"(JSON 확장 표기와
# 문자열 모두 pydantic이 float로 받아 준다)과 1e300 같은 값이 통과해서, 충전 시간
# 0초·비용 0원짜리 200이나 timedelta 오버플로 500이 났다. 상한은 "실제로 있는
# 값 + 넉넉한 여유"다: 승용 전기차 배터리는 100kWh대, 대형 버스도 수백 kWh이고,
# 가장 빠른 충전기가 1MW급이다. 공공 급속 단가는 kWh당 수백 원대다.
MAX_BATTERY_KWH = 1000
MAX_CHARGER_KW = 1000
MAX_PRICE_PER_KWH = 10_000


class RecommendRequest(BaseModel):
    battery_kwh: float | None = Field(
        default=None, gt=0, le=MAX_BATTERY_KWH, allow_inf_nan=False
    )
    soc_now: float = Field(ge=0, lt=100, allow_inf_nan=False)
    soc_target: float = Field(gt=0, le=100, allow_inf_nan=False)
    charger_kw: float | None = Field(default=None, gt=0, le=MAX_CHARGER_KW, allow_inf_nan=False)
    earliest_start: datetime
    deadline: datetime
    mode: Mode = "self_low"
    public_base_price: float | None = Field(
        default=None, gt=0, le=MAX_PRICE_PER_KWH, allow_inf_nan=False
    )
    efficiency: float = Field(default=1.0, gt=0, le=1, allow_inf_nan=False)
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
    def _check_ranges(self) -> RecommendRequest:
        if self.soc_target <= self.soc_now:
            raise ValueError("soc_target은 soc_now보다 커야 합니다.")
        if self.deadline <= self.earliest_start:
            raise ValueError("deadline은 earliest_start보다 뒤여야 합니다.")
        if self.deadline - self.earliest_start > MAX_REQUEST_SPAN:
            raise ValueError(
                f"earliest_start와 deadline 사이는 {MAX_REQUEST_SPAN.days}일을 "
                "넘을 수 없습니다."
            )
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
    battery_kwh: float = Field(gt=0, le=MAX_BATTERY_KWH, allow_inf_nan=False)
    charger_kw: float = Field(gt=0, le=MAX_CHARGER_KW, allow_inf_nan=False)
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
    battery_kwh: float | None = Field(
        default=None, gt=0, le=MAX_BATTERY_KWH, allow_inf_nan=False
    )
    charger_kw: float | None = Field(default=None, gt=0, le=MAX_CHARGER_KW, allow_inf_nan=False)
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
    """F-09 시간별 예측.

    ``predicted_mwh``가 optional인 이유는 ``api/solar_service.py`` 머리말에
    자세히 적었다. 요약하면: 물리 모델이 내놓는 것은 단위면적당 일사량이고,
    MWh로 바꾸려면 지역 태양광 설비용량(전력거래소 자료)이 필요한데 지금
    없다. 없는 자료로 숫자를 지어내는 대신 null로 비우고, 실제로 계산되는
    값(``ghi_wm2``·``output_index``)을 함께 내보낸다.
    """

    hour: int
    # 구름·강수를 반영한 수평면 전일사량. 이 모델의 실제 출력이다.
    ghi_wm2: float
    # 같은 시각의 맑은날 값. 구름이 얼마나 깎았는지 화면에서 바로 보인다.
    clear_sky_ghi_wm2: float
    # STC(1000 W/m²) 대비 0~1. 요금 차트에 겹쳐 그릴 때 쓰는 값이다.
    output_index: float
    # 설비용량이 설정됐을 때만 채워진다. 기본은 null.
    predicted_mwh: float | None = None
    # 기상청 원본 코드. 감쇠가 맞는지 사람이 되짚을 수 있게 그대로 싣는다.
    sky: str
    pty: str


class SolarForecast(BaseModel):
    region: str
    day: date
    # 물리 모델이므로 "계산식의 버전"이다 (domain/solar.py의 MODEL_VERSION).
    model_version: str
    hours: list[SolarHour]
    # 어느 격자·어느 발표를 썼는지. 한 격자가 시도 전체를 대신한다는 사실을
    # 응답이 숨기지 않게 한다.
    grid_nx: int
    grid_ny: int
    base_date: str
    base_time: str
    installed_capacity_mw: float | None = None
    capacity_source: str | None = None
    # RecommendResponse.assumptions와 같은 역할 — 이 값을 어떤 전제로 냈는지.
    assumptions: list[str] = []


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None


class ChatResponse(BaseModel):
    answer: str
    recommendation: RecommendResponse | None = None
    missing_fields: list[str] = []


# ── 차량 앱 (Pleos Connect) ─────────────────────────────────────────────
# 계약: docs/car-api.md. 차량 앱은 로그인 없이(게스트) 쓴다.


MIN_BATTERY_CAPACITY_WH = 1000


class CarPlanRequest(BaseModel):
    """``POST /api/car/plan`` 요청. 차량이 아는 값으로 충전 계획을 묻는다.

    ``soc_target <= soc_now``는 오류가 아니다 — "충전 필요 없음" 응답으로
    답하므로 ``RecommendRequest``와 달리 여기서 막지 않는다. 시각의 앞뒤 검사는
    ``plug_in_at``이 빠졌을 때 서버 현재 시각이 들어가야 해서 계산 서비스
    (``car_plan_service``)에서 한다.
    """

    soc_now: float = Field(ge=0, lt=100, allow_inf_nan=False)
    # Pleos Vehicle SDK getEvBatteryCapacity가 Wh로 준다. 서버가 kWh로 바꾼다.
    # 하한 1,000Wh(1kWh): 그보다 작은 값은 실제 차에서 오지 않고, 5e-324처럼 아주
    # 작은 값은 충전 시간이 0이 되어 500이 나거나 "22:00 시작, 22:00 종료" 같은
    # 예약을 만든다.
    battery_capacity_wh: float = Field(
        ge=MIN_BATTERY_CAPACITY_WH, le=MAX_BATTERY_KWH * 1000, allow_inf_nan=False
    )
    soc_target: float = Field(default=80, gt=0, le=100, allow_inf_nan=False)
    charger_kw: float = Field(default=7.0, gt=0, le=MAX_CHARGER_KW, allow_inf_nan=False)
    plug_in_at: datetime | None = None
    depart_at: datetime
    mode: Mode = "self_low"

    @field_validator("plug_in_at", "depart_at")
    @classmethod
    def _normalize_to_kst(cls, value: datetime | None) -> datetime | None:
        """``RecommendRequest``와 같은 규칙: 오프셋이 없으면 KST로 읽는다."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=KST)
        return value.astimezone(KST)


class ReservationOut(BaseModel):
    """차량 기본 예약 충전에 넣을 값. 시작은 꽂는 시각 이후, 종료는 분 단위 올림."""

    start_at: KstDatetime
    end_at: KstDatetime
    start_hhmm: str
    end_hhmm: str


class CarPlanResponse(BaseModel):
    needs_charging: bool
    plan: ChargePlanOut | None = None
    baseline_now: ChargePlanOut | None = None
    savings_won: int | None = None
    reservation: ReservationOut | None = None
    # TTS가 그대로 읽는 문장. 숫자는 전부 위 계산값이나 요청 값에서 온다.
    speech: str
    assumptions: list[str]
    unverified_tariff_items: list[str]
    # 기기 토큰과 함께 와서 대기 절감 기록을 만들었을 때만 채운다 (BE-5). 아니면 null.
    saving_id: str | None = None


class CarLeakCheckRequest(BaseModel):
    """``POST /api/car/leak-check`` 요청. 계약: docs/car-api.md.

    ``place``에 따라 쓰는 필드가 다르다. home은 ``depart_at``·``mode``를, public은
    ``payment``·``charger_speed``를 쓰고 다른 쪽 필드는 무시한다. public에서
    ``payment``·``charger_speed``가 빠졌는지는 서비스(``car_leak_service``)가 보고
    필드 위치를 담은 422를 낸다.
    """

    place: Literal["home", "public"] = "home"
    soc_now: float = Field(ge=0, lt=100, allow_inf_nan=False)
    battery_capacity_wh: float = Field(
        ge=MIN_BATTERY_CAPACITY_WH, le=MAX_BATTERY_KWH * 1000, allow_inf_nan=False
    )
    soc_target: float = Field(default=80, gt=0, le=100, allow_inf_nan=False)
    charger_kw: float = Field(default=7.0, gt=0, le=MAX_CHARGER_KW, allow_inf_nan=False)
    depart_at: datetime | None = None
    mode: Mode = "self_low"
    payment: Literal["member", "roaming", "nonmember"] | None = None
    charger_speed: Literal["slow", "fast"] | None = None

    @field_validator("depart_at")
    @classmethod
    def _normalize_to_kst(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=KST)
        return value.astimezone(KST)


class CarLeakCheckResponse(BaseModel):
    leaking: bool
    leak_won: int
    cause: Literal["time", "payment"] | None = None
    energy_kwh: float
    # home에서 돈이 샐 때만: 가장 싼 구간과 차량 예약 충전 값 (car/plan과 같은 모양)
    plan: ChargePlanOut | None = None
    reservation: ReservationOut | None = None
    # public일 때만: 지금 결제 방식과 회원가의 사업자 평균 단가(원/kWh)
    unit_price_now: float | None = None
    unit_price_member: float | None = None
    speech: str
    assumptions: list[str]
    # 기기 토큰과 함께 와서 대기 절감 기록을 만들었을 때만 채운다 (BE-5). 아니면 null.
    saving_id: str | None = None


class CarDeviceOut(BaseModel):
    """``POST /api/car/devices`` 201. 토큰은 이 응답에서 한 번만 보인다."""

    device_id: str
    device_token: str
