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
from datetime import datetime

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from ..infra.db import session_scope
from ..infra.models import MAX_CAR_SAVING_WON, CarDevice, CarSaving
from .car_devices import bearer_token, find_device

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
    """확정. 이미 확정됐으면 그대로 돌려준다(멱등). 이 기기의 기록이 아니면 None."""
    try:
        uuid.UUID(saving_id)
    except ValueError:
        return None
    saving = session.scalar(
        select(CarSaving)
        .where(CarSaving.id == saving_id, CarSaving.device_id == device.id)
        .with_for_update()
    )
    if saving is None:
        return None
    if saving.confirmed_at is None:
        saving.confirmed_at = now
    session.commit()
    return saving
