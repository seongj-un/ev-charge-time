"""API 명세서 6장의 테이블 5개.

이번 단계에서는 어느 라우터도 이 테이블을 쓰지 않는다. 인증·사용자 데이터
구현 때 바로 쓸 수 있도록 스키마만 세워둔다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = _now()

    vehicles: Mapped[list[Vehicle]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    battery_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    charger_kw: Mapped[float] = mapped_column(Float, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="self_low")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _now()

    user: Mapped[User] = relationship(back_populates="vehicles")

    __table_args__ = (
        # 사용자당 기본 차량은 1대 (F-12)
        Index(
            "uq_vehicles_one_default_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )


class SavedPlan(Base):
    __tablename__ = "saved_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 저장 당시 요금 설정 버전. 요금이 바뀌어도 재계산하지 않는다 (F-13)
    tariff_version: Mapped[str] = mapped_column(String(50), nullable=False)
    # 저장 당시 차량 이름 스냅샷 (3번 수정). tariff_version과 같은 이유로
    # nullable로 둔다 — vehicle_id로 저장했으면 그 시점 이름을, 직접 입력이면
    # None을 담는다. 차량이 나중에 지워지거나 이름이 바뀌어도 "그때 무엇으로
    # 계획했는지"는 이 스냅샷에 그대로 남아야 한다(FK가 아니라 이름 문자열인 이유).
    vehicle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 충전이 시작되는 시각 = result["best"]["start"] (4번 수정).
    #
    # result가 JSONB라 (result->'best'->>'start')::timestamptz로 매번 캐스팅해
    # 거를 수도 있지만, 저장 시점에 뽑아 컬럼으로 둔다: 인덱스를 태울 수 있고,
    # JSONB 경로 오타가 런타임에야 드러나는 일이 없다. tariff_version·
    # vehicle_name과 같은 "저장 당시 값 스냅샷"이기도 하다.
    #
    # 월 필터와 목록 정렬이 둘 다 이 컬럼을 기준으로 한다 — 사용자가 보는
    # 날짜가 충전 날짜이므로, 거르는 기준과 보이는 기준이 같아야 한다.
    charge_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = _now()


class FavoriteStation(Base):
    __tablename__ = "favorite_stations"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # 이름·주소는 저장하지 않는다. 조회 시 charger_cache에서 (F-14)
    station_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = _now()

    __table_args__ = (
        UniqueConstraint("user_id", "station_id", name="uq_favorite_user_station"),
    )


class Session(Base):
    """로그인 세션. 토큰 원본이 아니라 sha256 해시만 저장한다 (infra/security.py)."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = _now()


class LoginAttempt(Base):
    """이메일별 로그인 실패 횟수·잠금 상태 (연속 5회 실패 시 15분 잠금)."""

    __tablename__ = "login_attempts"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    # server_default도 둔다: ORM의 default=0은 SQLAlchemy를 거친 INSERT에만 적용되고,
    # raw INSERT(마이그레이션 스크립트, 다른 도구 등)는 우회해 NOT NULL을 위반할 수 있다.
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ChatRateLimit(Base):
    """F-10 자연어 질의의 사용자별 호출 제한 (고정 창 카운터).

    **사용자당 한 행이다.** (user_id, window_start) 복합키로 창마다 새 행을
    쌓지 않는 이유: 그러면 지난 창의 행이 영영 남아 따로 청소해 줘야 한다.
    대신 ``window_start``를 값으로 들고 다니면서, UPSERT 한 문장이 "같은
    창이면 +1, 창이 넘어갔으면 1로 초기화"를 함께 처리한다
    (``routes/extensions.py``의 ``_consume_quota``).

    카운터를 애플리케이션에서 읽고-쓰지 않는 것이 핵심이다 —
    ``login_attempts.failed_count``가 정확히 그 방식이라 병렬 요청에 증가분을
    잃어버렸고(lost update), 순차 5회는 잠기는데 병렬 5회는 안 잠겼다.
    """

    __tablename__ = "chat_rate_limits"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # 이 카운터가 속한 고정 창의 시작 시각. 요청이 들어온 창과 다르면
    # used_count를 1로 되돌린다.
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # server_default도 둔다 — login_attempts.failed_count와 같은 이유로,
    # SQLAlchemy를 거치지 않는 raw INSERT가 NOT NULL을 위반하지 않게.
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ChatServiceQuota(Base):
    """F-10 자연어 질의의 **서비스 전체** 호출 제한 (고정 창 카운터).

    사용자별 제한(``ChatRateLimit``)만으로는 공개 서버를 지킬 수 없다.
    회원가입이 열려 있으면 계정을 여러 개 만드는 것으로 "사용자당 N회"가
    사실상 무제한이 되는데, **무료 티어의 일일 할당량은 프로젝트 전체에**
    걸린다. 한 사람이 공용 예산을 비우면 그날 나머지 모두의 질문이 막힌다.

    본선 시연 중에 그 일이 나는 것이 최악이라, 사용자 한도와 별개로
    서비스 전체 한도를 하나 더 둔다.

    **행은 영원히 하나다.** ``id``를 1로 고정하고 ``window_start``를 값으로
    들고 다니면서, UPSERT 한 문장이 "같은 창이면 +1, 창이 넘어갔으면 1로
    초기화"를 처리한다. ``ChatRateLimit``과 같은 이유로 읽고-쓰기를 하지
    않는다 — 병렬 요청에 증가분을 잃으면 한도가 우회된다.
    """

    __tablename__ = "chat_service_quota"

    # 항상 1. 이 테이블은 행 하나짜리 카운터다.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ChargerCache(Base):
    __tablename__ = "charger_cache"

    # 전 사용자 공유 캐시. 사용자가 늘어도 공공 API 호출량은 그대로 (F-07)
    station_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 좌표는 data JSONB 안에도 들어 있지만 컬럼으로 한 번 더 꺼내 둔다.
    # 반경 조회의 1차 필터(바운딩 박스)가 매 요청 JSONB 캐스팅을 하면 인덱스를
    # 못 타고 3만 건을 통째로 훑는다 — saved_plans.charge_start를 뽑았던 것과
    # 같은 이유다. 아래 복합 인덱스가 그 범위 비교를 받는다.
    #
    # nullable인 이유: 좌표 없는 행이 정상적으로 존재한다. 수집기는 좌표가
    # 없는 충전소를 캐시에 넣지 않지만, 캐시 행을 직접 만드는 다른 경로(테스트
    # 픽스처 등)가 좌표를 모를 수 있다. 그런 행은 반경 조회에 잡히지 않을 뿐
    # 즐겨찾기 조회(F-14)에서는 그대로 쓰인다.
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_charger_cache_lat_lng", "lat", "lng"),)


# ── 와트잇 차량 앱 (BE-5 절약 리포트) ─────────────────────────────────────
# 차량 앱은 로그인이 없다. 기기마다 토큰 하나를 발급하고 해시만 저장한다
# (세션 토큰과 같은 방식, infra/security.py). 개인정보는 담지 않는다.

# 1회 기록 상한(원). 서버 계산값이지만 공개 엔드포인트라 합계를 부풀리는 입력
# (아주 큰 배터리 등)을 한 건으로 막는다. api/car_savings.py와 같은 값이다.
MAX_CAR_SAVING_WON = 100_000


class CarDevice(Base):
    __tablename__ = "car_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # sha256 hex. 토큰 원본은 발급 응답에 한 번만 나간다.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = _now()
    last_seen_at: Mapped[datetime] = _now()


class CarSaving(Base):
    """추천을 따랐을 때 아낀 금액 한 건 (서버 계산값, 실측 요금 아님).

    ``confirmed_at``이 비어 있으면 대기 중이다. 앱이 실제로 따랐다고 확인해야
    (``POST /api/car/savings/{id}/confirm``) 합산에 들어간다. 대기 기록은 기기당
    최근 20개만 남긴다.
    """

    __tablename__ = "car_savings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("car_devices.id", ondelete="CASCADE"), nullable=False
    )
    cause: Mapped[str] = mapped_column(String(10), nullable=False)
    savings_won: Mapped[int] = mapped_column(Integer, nullable=False)
    energy_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = _now()
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("cause IN ('time', 'payment')", name="ck_car_savings_cause"),
        CheckConstraint("source IN ('plan', 'leak_check')", name="ck_car_savings_source"),
        CheckConstraint(
            f"savings_won >= 0 AND savings_won <= {MAX_CAR_SAVING_WON}",
            name="ck_car_savings_won_range",
        ),
        # 합산(확정분을 confirmed_at 구간으로)과 대기 기록 정리(대기분을 created_at
        # 순으로) 모두 기기별로 읽는다.
        Index("ix_car_savings_device_confirmed", "device_id", "confirmed_at"),
        Index("ix_car_savings_device_created", "device_id", "created_at"),
    )


class CarDeviceRateLimit(Base):
    """기기 발급(``POST /api/car/devices``)의 IP별 고정 창 카운터.

    ``ChatRateLimit``과 같은 방식이다: IP당 한 행, UPSERT 한 문장으로 창이 같으면
    +1, 넘어갔으면 1. IP 원문은 저장하지 않고 가명 처리한 키만 둔다
    (``CAR_IP_HASH_SECRET``으로 만든 HMAC-SHA256, 비밀값이 없으면 sha256 —
    ``api/car_devices.ip_key``).
    """

    __tablename__ = "car_device_rate_limits"

    ip_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CarVoiceRateLimit(Base):
    """음성 대화(``POST /api/car/voice``)의 기기별 하루(KST) 카운터 (BE-3).

    ``ChatRateLimit``과 같은 방식이다: 기기당 한 행, UPSERT 한 문장으로 같은 날이면
    +1, 날이 바뀌었으면 1 (``api/car_voice_quota.py``).
    """

    __tablename__ = "car_voice_rate_limits"

    device_id: Mapped[str] = mapped_column(
        ForeignKey("car_devices.id", ondelete="CASCADE"), primary_key=True
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CarVoiceServiceQuota(Base):
    """음성 대화의 서비스 전체 하루(KST) 카운터 (BE-3). ``ChatServiceQuota``와 같이 행은
    ``id=1`` 하나뿐이다. 기기 토큰은 누구나 받을 수 있어서 기기별 한도만으로는 Claude
    비용을 막지 못한다.
    """

    __tablename__ = "car_voice_service_quota"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
