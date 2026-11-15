"""와트잇 출발 시각 학습 (BE-8): 기록, 삭제, 평소 출발 시각 제안.

편의 1순위: 출발 시각을 묻지 않고, 틀린 "오전 8시" 가정을 줄인다. 규칙은
``domain/departures.py``, 계약은 ``docs/car-api.md`` "출발 시각 학습" 절.

기록
- ``observed``: ``POST /api/car/departures``(앱이 기어가 P에서 벗어난 첫 시각)
- ``stated``: 계산 요청에 운전자가 직접 넣은 출발 시각(car/plan, car/leak-check home,
  음성 plan_charge). 서버가 가정한 시각은 남기지 않는다. 기록은 계산 뒤에 붙는 부가
  작업이라 실패해도 계산 응답은 그대로다(``try_record_stated``).

남기는 규칙
- 같은 기기 30분 안의 기록은 하나로 합친다. observed가 stated를 대신하고, observed끼리는
  이른 시각(처음 P를 벗어난 때), stated끼리는 나중에 말한 시각을 남긴다.
- 기기당 하루(KST, 기록한 날) 10건까지 새로 만든다. 넘으면 observed는 429, stated는 남기지 않는다.
- 출발 시각이 90일 지난 기록은 기록할 때마다 (모든 기기에서) 지운다.
- ``DELETE /api/car/departures``는 그 기기의 기록을 전부 지운다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta
from math import ceil

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as DbSession

from ..domain.calendar import HolidayProvider
from ..domain.departures import DepartureRecord, DepartureSuggestion, suggest, window
from ..domain.errors import DomainError
from ..domain.pricing import KST
from ..infra.db import session_scope
from ..infra.models import CarDeparture, CarDevice
from .car_devices import bearer_token, find_device
from .car_plan_service import spoken_clock
from .schemas import CarDepartureSuggestion

logger = logging.getLogger(__name__)

MERGE_WINDOW = timedelta(minutes=30)
DAILY_MAX = 10
RETENTION = timedelta(days=90)
# 앱 시계와 서버 시계가 조금 어긋나도 방금 출발한 기록을 받는다.
CLOCK_SKEW = timedelta(minutes=5)
# 운전자가 말한 출발 시각은 미래다. 계산 API의 상한(72시간)보다 길게 받을 일이 없다.
STATED_AHEAD = timedelta(hours=72)


class DepartureLimitError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("daily departure limit")
        self.retry_after = retry_after


def record_departure(
    session: DbSession, device: CarDevice, departed_at: datetime, source: str, now: datetime
) -> tuple[CarDeparture, bool]:
    """기록하고 ``(기록, 새로 만들었는지)``를 돌려준다. 커밋까지 한다.

    기기 행을 ``FOR UPDATE``로 잡은 뒤 중복을 찾고 하루 건수를 센다. 같은 기기의 동시
    기록이 여기서 줄을 서므로, 둘 다 "중복 없음"이나 "아직 9건"을 읽지 않는다.
    """
    session.execute(select(CarDevice.id).where(CarDevice.id == device.id).with_for_update())
    session.execute(delete(CarDeparture).where(CarDeparture.departed_at < now - RETENTION))

    nearby = session.scalar(
        select(CarDeparture)
        .where(
            CarDeparture.device_id == device.id,
            CarDeparture.departed_at >= departed_at - MERGE_WINDOW,
            CarDeparture.departed_at <= departed_at + MERGE_WINDOW,
        )
        .order_by(func.abs(func.extract("epoch", CarDeparture.departed_at - departed_at)))
        .limit(1)
    )
    if nearby is not None:
        _merge(nearby, departed_at, source)
        session.commit()
        return nearby, False

    local = now.astimezone(KST)
    day_start = datetime.combine(local.date(), time(), tzinfo=KST)
    day_end = day_start + timedelta(days=1)
    used = session.scalar(
        select(func.count()).where(
            CarDeparture.device_id == device.id,
            CarDeparture.recorded_at >= day_start,
            CarDeparture.recorded_at < day_end,
        )
    )
    if used >= DAILY_MAX:
        session.rollback()
        raise DepartureLimitError(max(1, ceil((day_end - now).total_seconds())))

    departure = CarDeparture(
        id=str(uuid.uuid4()),
        device_id=device.id,
        departed_at=departed_at,
        source=source,
        recorded_at=now,
    )
    session.add(departure)
    session.commit()
    return departure, True


def _merge(existing: CarDeparture, departed_at: datetime, source: str) -> None:
    if source == "observed" and existing.source == "stated":
        existing.source, existing.departed_at = "observed", departed_at
    elif source == existing.source == "observed":
        existing.departed_at = min(existing.departed_at, departed_at)
    elif source == existing.source == "stated":
        existing.departed_at = departed_at
    # stated가 observed 옆에 오면 실제 출발을 그대로 둔다.


def check_observed_time(departed_at: datetime, now: datetime) -> None:
    """관찰 시각은 지금(+5분)보다 늦을 수 없고, 90일보다 오래될 수 없다. 아니면 422."""
    if departed_at > now + CLOCK_SKEW:
        _reject("departed_at은 지금보다 늦을 수 없습니다.", departed_at)
    if departed_at < now - RETENTION:
        _reject("departed_at은 90일 안이어야 합니다.", departed_at)


def _reject(message: str, value: datetime) -> None:
    raise RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "departed_at"),
                "msg": message,
                "input": value.isoformat(),
            }
        ]
    )


def delete_departures(session: DbSession, device: CarDevice) -> int:
    result = session.execute(delete(CarDeparture).where(CarDeparture.device_id == device.id))
    session.commit()
    return result.rowcount or 0


def raise_limit(exc: DepartureLimitError) -> None:
    raise HTTPException(
        status_code=429,
        detail=f"오늘 남길 수 있는 출발 기록({DAILY_MAX}건)을 다 썼습니다. 내일 다시 보내 주세요.",
        headers={"Retry-After": str(exc.retry_after)},
    )


# ---------------------------------------------------------------------------
# stated: 계산 요청에 운전자가 넣은 출발 시각
# ---------------------------------------------------------------------------


def record_stated(
    session: DbSession, device: CarDevice, depart_at: datetime, now: datetime
) -> bool:
    """운전자가 말한 출발 시각을 남긴다. 범위 밖·하루 상한이면 조용히 건너뛴다(False)."""
    if not now - RETENTION <= depart_at <= now + STATED_AHEAD:
        return False
    try:
        record_departure(session, device, depart_at, "stated", now)
    except DepartureLimitError:
        return False
    return True


def try_record_stated(request: Request, depart_at: datetime, now: datetime) -> None:
    """계산 엔드포인트용. 토큰이 없으면 DB를 열지 않고, 실패해도 계산 응답은 그대로다."""
    token = bearer_token(request)
    if token is None:
        return
    try:
        with session_scope(request.app.dependency_overrides) as session:
            try:
                device = find_device(session, token)
                if device is not None:
                    record_stated(session, device, depart_at, now)
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise
    except SQLAlchemyError:
        logger.warning("출발 기록을 남기지 못했습니다 (stated)", exc_info=True)


# ---------------------------------------------------------------------------
# 제안
# ---------------------------------------------------------------------------


def suggestion_for(
    session: DbSession, device: CarDevice, target: date, holidays: HolidayProvider
) -> DepartureSuggestion:
    start, end = window(target)
    rows = session.execute(
        select(CarDeparture.departed_at, CarDeparture.source).where(
            CarDeparture.device_id == device.id,
            CarDeparture.departed_at >= start,
            CarDeparture.departed_at < end,
        )
    ).all()
    records = [DepartureRecord(departed_at, source) for departed_at, source in rows]
    return suggest(records, target, holidays)


def next_usual_departure(
    session: DbSession, device: CarDevice, now: datetime, holidays: HolidayProvider
) -> DepartureSuggestion | None:
    """다음 출발의 제안. 정오 전이면 오늘, 아니면 내일. 오늘 제안 시각이 지났으면 내일.

    제안이 없거나(기록 부족) 계산할 수 없으면(공휴일 정보 없음, DB 오류) None이다.
    부르는 쪽(leak-check, 음성)은 이때 지금처럼 동작한다.
    """
    local = now.astimezone(KST)
    today = local.date()
    target = today if local.hour < 12 else today + timedelta(days=1)
    try:
        found = suggestion_for(session, device, target, holidays)
        if found.depart_at is not None and found.depart_at <= local and target == today:
            found = suggestion_for(session, device, today + timedelta(days=1), holidays)
    except (DomainError, SQLAlchemyError):
        session.rollback()
        logger.warning("평소 출발 시각을 계산하지 못했습니다", exc_info=True)
        return None
    if found.depart_at is None or found.depart_at <= local:
        return None
    return found


def day_label(target: date, now: datetime) -> str:
    today = now.astimezone(KST).date()
    if target == today:
        return "오늘"
    if target == today + timedelta(days=1):
        return "내일"
    return f"{target.month}월 {target.day}일"


def suggestion_question(found: DepartureSuggestion, now: datetime) -> str:
    """제안 문장. high: "내일도 오전 7시 30분에 출발하세요?", low: "…쯤 출발하세요?"."""
    label = day_label(found.target, now)
    if found.depart_at is None:
        return f"{label} 몇 시에 출발하세요?"
    clock = spoken_clock(found.depart_at.astimezone(KST))
    if found.confidence == "high":
        return f"{label}도 {clock}에 출발하세요?"
    return f"{label} {clock}쯤 출발하세요?"


def to_suggestion_out(found: DepartureSuggestion, now: datetime) -> CarDepartureSuggestion:
    return CarDepartureSuggestion(
        date=found.target,
        suggested_depart_at=found.depart_at,
        confidence=found.confidence,
        basis_count=found.basis_count,
        day_type=found.day_type,
        speech=suggestion_question(found, now),
    )
