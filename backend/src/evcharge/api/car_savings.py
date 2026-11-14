"""와트잇 절감 기록 (BE-5): 대기 기록, 확정, 월·년 합산.

기록하는 금액은 전부 서버 계산값이다(``car/plan``의 ``savings_won``, ``car/leak-check``의
``leak_won``). 실측 요금이 아니라 "추천을 따랐을 때 아낀 금액"이다.

흐름
1. ``car/plan``·``car/leak-check``가 유효한 기기 토큰과 함께 오고 아끼는 돈이 있으면
   대기 기록을 만들고 ``saving_id``를 돌려준다. 토큰이 없으면 DB를 건드리지 않는다.
   기록이 실패해도(DB 오류) 계산 응답은 그대로 나간다 — 계산이 본 기능이다.
2. 앱이 실제로 따랐다고 확인하면 ``confirm``으로 확정한다. 확정분만 합산한다.
3. 대기 기록은 기기당 최근 20개만 남긴다. 확정 안 된 채 쌓이는 것을 막는다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, time, timedelta
from math import ceil

from fastapi import HTTPException, Request
from sqlalchemy import and_, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from ..domain.pricing import KST
from ..infra.db import session_scope
from ..infra.models import MAX_CAR_SAVING_WON, CarDevice, CarSaving
from ..settings import get_settings
from .car_devices import bearer_token, find_device
from .months import month_bounds, month_of, year_bounds
from .schemas import CarSavingOut, CarSavingsByCause, CarSavingsSummary

logger = logging.getLogger(__name__)

MAX_PENDING_PER_DEVICE = 20


def record_pending(
    session: DbSession,
    device: CarDevice,
    *,
    cause: str,
    savings_won: int,
    energy_kwh: float,
    source: str,
) -> str:
    """대기 기록 하나를 만들고, 그 기기의 대기 기록을 최근 20개로 줄인 뒤 커밋한다.

    ``created_at``은 ``clock_timestamp()``다. ``now()``는 트랜잭션 시작 시각이라 한
    트랜잭션 안에서 여러 건을 만들면 같은 값이 되어 "최근 20개"를 가를 수 없다.
    """
    saving = CarSaving(
        id=str(uuid.uuid4()),
        device_id=device.id,
        cause=cause,
        savings_won=min(max(savings_won, 0), MAX_CAR_SAVING_WON),
        energy_kwh=energy_kwh,
        source=source,
        created_at=func.clock_timestamp(),
    )
    session.add(saving)
    session.flush()

    keep = (
        select(CarSaving.id)
        .where(CarSaving.device_id == device.id, CarSaving.confirmed_at.is_(None))
        .order_by(CarSaving.created_at.desc(), CarSaving.id.desc())
        .limit(MAX_PENDING_PER_DEVICE)
    )
    session.execute(
        delete(CarSaving).where(
            CarSaving.device_id == device.id,
            CarSaving.confirmed_at.is_(None),
            CarSaving.id.not_in(keep.scalar_subquery()),
        )
    )
    session.commit()
    return saving.id


def try_record(
    request: Request, *, cause: str, savings_won: int, energy_kwh: float, source: str
) -> str | None:
    """계산 엔드포인트용. 토큰이 없거나 틀리거나 DB가 실패하면 None (계산은 그대로).

    토큰이 없으면 DB 세션을 열지 않는다 — 기기 토큰 없이 쓰는 계산은 지금처럼 DB와
    무관해야 한다.
    """
    token = bearer_token(request)
    if token is None or savings_won <= 0:
        return None
    try:
        with session_scope(request.app.dependency_overrides) as session:
            try:
                device = find_device(session, token)
                if device is None:
                    return None
                return record_pending(
                    session,
                    device,
                    cause=cause,
                    savings_won=savings_won,
                    energy_kwh=energy_kwh,
                    source=source,
                )
            except SQLAlchemyError:
                session.rollback()
                raise
    except SQLAlchemyError:
        # 기록은 계산 뒤에 붙는 부가 작업이다. 실패해도 계산 응답을 실패로 만들지 않는다.
        logger.warning("절감 기록을 남기지 못했습니다 (source=%s)", source, exc_info=True)
        return None


def confirm(
    session: DbSession, device: CarDevice, saving_id: str, now: datetime
) -> CarSaving | None:
    """확정. 이 기기의 기록이 아니면 None(→ 404).

    - 이미 확정됐으면 그대로 돌려준다(멱등). 하루 한도를 쓰지 않는다.
    - 기록을 만든 뒤 ``car_savings_confirm_window_hours``가 지났으면 410.
    - 이 기기가 오늘(KST) 이미 ``car_savings_daily_confirm_max``건 확정했으면 429.

    하루 건수를 세기 전에 **기기 행을 ``FOR UPDATE``로 잡는다.** 같은 기기의 확정이
    여기서 줄을 서므로, 병렬 요청이 모두 "아직 2건"을 읽고 한도를 넘는 일이 없다.

    확정 기한은 DB 시계(``clock_timestamp()``)로 잰다. ``created_at``이 DB 시계로
    찍히기 때문이다. 하루 경계와 ``confirmed_at``은 앱 시계(``now``)다.
    """
    try:
        uuid.UUID(saving_id)
    except ValueError:
        return None
    settings = get_settings()

    session.execute(select(CarDevice.id).where(CarDevice.id == device.id).with_for_update())
    saving = session.scalar(
        select(CarSaving)
        .where(CarSaving.id == saving_id, CarSaving.device_id == device.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if saving is None:
        return None
    if saving.confirmed_at is not None:
        session.commit()
        return saving

    window = timedelta(hours=settings.car_savings_confirm_window_hours)
    db_now = session.scalar(select(func.clock_timestamp()))
    if db_now - saving.created_at > window:
        raise HTTPException(
            status_code=410,
            detail=(
                f"이 기록은 확정할 수 있는 기간({settings.car_savings_confirm_window_hours}시간)이 "
                "지났습니다."
            ),
        )

    local = now.astimezone(KST)
    day_start = datetime.combine(local.date(), time(), tzinfo=KST)
    day_end = day_start + timedelta(days=1)
    used = session.scalar(
        select(func.count()).where(
            CarSaving.device_id == device.id,
            CarSaving.confirmed_at >= day_start,
            CarSaving.confirmed_at < day_end,
        )
    )
    limit = settings.car_savings_daily_confirm_max
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"오늘 확정할 수 있는 횟수({limit}건)를 다 썼습니다. 내일 다시 확정해 주세요.",
            headers={"Retry-After": str(max(1, ceil((day_end - now).total_seconds())))},
        )

    saving.confirmed_at = now
    session.commit()
    return saving


def to_out(saving: CarSaving) -> CarSavingOut:
    return CarSavingOut(
        saving_id=saving.id,
        cause=saving.cause,
        savings_won=saving.savings_won,
        energy_kwh=saving.energy_kwh,
        source=saving.source,
        created_at=saving.created_at,
        confirmed_at=saving.confirmed_at,
    )


NONE_SPEECH = "아직 아낀 기록이 없어요. 와트잇 추천대로 충전하면 여기에 쌓여요."
NOTE = "추천을 따랐을 때 아낀 금액(서버 계산값)이며 실제 청구 요금과 다를 수 있습니다."


def summarize(
    session: DbSession, device: CarDevice, month: str, now: datetime
) -> CarSavingsSummary:
    """그 달·그해·전체의 확정 기록 합계. 달·해는 KST, 확정 시각(``confirmed_at``) 기준이다.

    ``month``는 ``YYYY-MM``이고, 형식이 틀리면 ``month_bounds``가 422를 낸다.
    """
    month_start, month_end = month_bounds(month)
    year = month_start.year
    year_start, year_end = year_bounds(year)
    at = CarSaving.confirmed_at
    in_month = and_(at >= month_start, at < month_end)
    in_year = and_(at >= year_start, at < year_end)

    def won(condition=None):
        total = func.sum(CarSaving.savings_won)
        if condition is not None:
            total = total.filter(condition)
        return func.coalesce(total, 0)

    def count(condition):
        return func.count().filter(condition)

    row = session.execute(
        select(
            won(in_month),
            count(in_month),
            won(in_year),
            count(in_year),
            won(),
            func.count(),
            won(CarSaving.cause == "time"),
            won(CarSaving.cause == "payment"),
        ).where(CarSaving.device_id == device.id, at.is_not(None))
    ).one()
    month_won, month_count, year_won, year_count, total_won, total_count, time_won, pay_won = (
        int(value) for value in row
    )

    return CarSavingsSummary(
        month=month,
        month_won=month_won,
        month_count=month_count,
        year=year,
        year_won=year_won,
        year_count=year_count,
        total_won=total_won,
        by_cause=CarSavingsByCause(time_won=time_won, payment_won=pay_won),
        speech=summary_speech(
            month=month,
            month_won=month_won,
            month_count=month_count,
            year_won=year_won,
            total_won=total_won,
            total_count=total_count,
            now=now,
        ),
        note=NOTE,
    )


def summary_speech(
    *,
    month: str,
    month_won: int,
    month_count: int,
    year_won: int,
    total_won: int,
    total_count: int,
    now: datetime,
) -> str:
    """시동을 켤 때 TTS로 읽을 한 줄. 숫자는 합계 그대로다.

    지금 달·지금 해면 "이번 달"·"올해", 아니면 "11월"·"2025년 11월", "2025년 한 해".
    """
    if total_count == 0:
        return NONE_SPEECH
    year, month_num = (int(part) for part in month.split("-"))
    this_year = now.astimezone(KST).year
    if month == month_of(now):
        month_label = "이번 달"
    elif year == this_year:
        month_label = f"{month_num}월"
    else:
        month_label = f"{year}년 {month_num}월"
    year_label = "올해" if year == this_year else f"{year}년 한 해"

    if month_count > 0:
        return (
            f"{month_label} 와트잇으로 약 {month_won:,}원, "
            f"{year_label} 약 {year_won:,}원 아꼈어요."
        )
    return (
        f"{month_label}에는 아낀 기록이 없어요. "
        f"지금까지 와트잇으로 약 {total_won:,}원 아꼈어요."
    )
