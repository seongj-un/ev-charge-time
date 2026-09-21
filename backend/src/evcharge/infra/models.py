"""API 명세서 6장의 테이블 5개.

이번 단계에서는 어느 라우터도 이 테이블을 쓰지 않는다. 인증·사용자 데이터
구현 때 바로 쓸 수 있도록 스키마만 세워둔다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class ChargerCache(Base):
    __tablename__ = "charger_cache"

    # 전 사용자 공유 캐시. 사용자가 늘어도 공공 API 호출량은 그대로 (F-07)
    station_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
