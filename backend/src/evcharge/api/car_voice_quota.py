"""음성 대화(BE-3)의 기기별·서비스 전체 하루 한도.

``routes/extensions.py``의 chat 한도와 같은 방식이다: UPSERT **한 문장**으로 "같은 창이면
+1, 창이 넘어갔으면 1"을 처리해 병렬 요청에도 증가분을 잃지 않는다. 창은 KST 하루다.

순서는 기기 → IP → 서비스다. 앞 한도에 걸린 요청은 뒤 카운터를 깎지 않는다.

Claude를 부르기 **전에** 세고 커밋한다. 나중에 세면 실패하는 호출은 공짜가 되고, 실패한
호출도 비용은 나간다. 순서를 뒤집으면 어차피 앞 한도에 걸릴 요청이 공용 예산을 깎는다.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from math import ceil

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from ..domain.pricing import KST
from ..infra.models import CarDevice, CarVoiceIpLimit, CarVoiceRateLimit, CarVoiceServiceQuota
from ..settings import get_settings

logger = logging.getLogger(__name__)

DEVICE_LIMIT_SPEECH = "오늘은 음성 대화를 많이 쓰셔서 여기까지예요. 내일 다시 말씀해 주세요."
IP_LIMIT_SPEECH = (
    "이 네트워크에서 오늘 음성 대화를 많이 써서 여기까지예요. 내일 다시 말씀해 주세요."
)
SERVICE_LIMIT_SPEECH = (
    "지금은 음성 대화를 쓰는 분이 많아 오늘은 여기까지예요. 내일 다시 말씀해 주세요."
)


class VoiceQuotaExceededError(Exception):
    """한도 초과. 라우터가 429와 ``speech``로 바꾼다."""

    def __init__(self, scope: str, speech: str, retry_after: int) -> None:
        super().__init__(scope)
        self.scope = scope
        self.speech = speech
        self.retry_after = retry_after


def day_start(now: datetime) -> datetime:
    """``now``가 속한 KST 하루의 0시."""
    return datetime.combine(now.astimezone(KST).date(), time(), tzinfo=KST)


def consume_voice_quota(
    session: DbSession, device: CarDevice, ip_hash: str, now: datetime
) -> None:
    """이번 요청분을 기기, IP, 서비스 순서로 차감한다. 넘으면 ``VoiceQuotaExceededError``.

    ``ip_hash``는 ``car_devices.ip_key``로 가명 처리한 값이다.
    """
    settings = get_settings()
    start = day_start(now)
    retry_after = max(1, ceil((start + timedelta(days=1) - now).total_seconds()))

    used = session.execute(
        pg_insert(CarVoiceRateLimit)
        .values(device_id=device.id, window_start=start, used_count=1)
        .on_conflict_do_update(
            index_elements=[CarVoiceRateLimit.device_id],
            set_={
                "used_count": case(
                    (
                        CarVoiceRateLimit.window_start == start,
                        CarVoiceRateLimit.used_count + 1,
                    ),
                    else_=1,
                ),
                "window_start": start,
            },
        )
        .returning(CarVoiceRateLimit.used_count)
    ).scalar_one()
    session.commit()
    if used > settings.car_voice_daily_max:
        raise VoiceQuotaExceededError("device", DEVICE_LIMIT_SPEECH, retry_after)

    used = session.execute(
        pg_insert(CarVoiceIpLimit)
        .values(ip_hash=ip_hash, window_start=start, used_count=1)
        .on_conflict_do_update(
            index_elements=[CarVoiceIpLimit.ip_hash],
            set_={
                "used_count": case(
                    (CarVoiceIpLimit.window_start == start, CarVoiceIpLimit.used_count + 1),
                    else_=1,
                ),
                "window_start": start,
            },
        )
        .returning(CarVoiceIpLimit.used_count)
    ).scalar_one()
    session.commit()
    if used > settings.car_voice_ip_daily_max:
        raise VoiceQuotaExceededError("ip", IP_LIMIT_SPEECH, retry_after)

    limit = settings.car_voice_service_daily_max
    if limit <= 0:
        return
    used = session.execute(
        pg_insert(CarVoiceServiceQuota)
        .values(id=1, window_start=start, used_count=1)
        .on_conflict_do_update(
            index_elements=[CarVoiceServiceQuota.id],
            set_={
                "used_count": case(
                    (
                        CarVoiceServiceQuota.window_start == start,
                        CarVoiceServiceQuota.used_count + 1,
                    ),
                    else_=1,
                ),
                "window_start": start,
            },
        )
        .returning(CarVoiceServiceQuota.used_count)
    ).scalar_one()
    session.commit()
    if used > limit:
        logger.warning("음성 대화 서비스 전체 한도 소진: %s/%s (%s)", used, limit, start.date())
        raise VoiceQuotaExceededError("service", SERVICE_LIMIT_SPEECH, retry_after)
