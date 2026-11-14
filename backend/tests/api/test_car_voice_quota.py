"""음성 대화의 기기별·서비스 전체 하루 한도 (``consume_voice_quota``)."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from evcharge.api.car_voice_quota import (
    DEVICE_LIMIT_SPEECH,
    IP_LIMIT_SPEECH,
    SERVICE_LIMIT_SPEECH,
    VoiceQuotaExceededError,
    consume_voice_quota,
    day_start,
)
from evcharge.domain.pricing import KST
from evcharge.infra.models import CarDevice, CarVoiceIpLimit, CarVoiceServiceQuota


def kst(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


def new_device(db_session) -> CarDevice:
    device = CarDevice(id=str(uuid.uuid4()), token_hash=uuid.uuid4().hex * 2)
    db_session.add(device)
    db_session.commit()
    return device


def spend(db_session, device: CarDevice, now: datetime, ip: str | None = None) -> None:
    """기기마다 다른 IP로 센다(IP 한도를 따로 시험하는 테스트만 ``ip``를 준다)."""
    consume_voice_quota(db_session, device, ip or f"ip-{device.id}"[:64], now)


def test_day_start_is_kst_midnight():
    assert day_start(kst(2026, 11, 16, 23, 59)) == kst(2026, 11, 16)
    # UTC 2026-11-15 15:00 = KST 2026-11-16 00:00
    assert day_start(datetime.fromisoformat("2026-11-15T15:00:00+00:00")) == kst(2026, 11, 16)


def test_device_limit_counts_per_device_and_resets_next_day(db_session, monkeypatch):
    monkeypatch.setenv("CAR_VOICE_DAILY_MAX", "2")
    mine, theirs = new_device(db_session), new_device(db_session)
    evening = kst(2026, 11, 16, 18)

    spend(db_session, mine, evening)
    spend(db_session, mine, evening)
    with pytest.raises(VoiceQuotaExceededError) as caught:
        spend(db_session, mine, evening)
    spend(db_session, theirs, evening)
    spend(db_session, mine, kst(2026, 11, 17, 0, 0))

    assert caught.value.scope == "device"
    assert caught.value.speech == DEVICE_LIMIT_SPEECH
    assert caught.value.retry_after == 6 * 3600


def test_service_limit_is_shared_by_all_devices(db_session, monkeypatch):
    monkeypatch.setenv("CAR_VOICE_SERVICE_DAILY_MAX", "2")
    db_session.query(CarVoiceServiceQuota).delete()
    db_session.commit()
    now = kst(2026, 11, 16, 23, 59, 30)

    spend(db_session, new_device(db_session), now)
    spend(db_session, new_device(db_session), now)
    with pytest.raises(VoiceQuotaExceededError) as caught:
        spend(db_session, new_device(db_session), now)

    assert caught.value.scope == "service"
    assert caught.value.speech == SERVICE_LIMIT_SPEECH
    assert caught.value.retry_after == 30
    # 다음 날 0시에는 다시 1부터 센다.
    spend(db_session, new_device(db_session), kst(2026, 11, 17))


def test_device_over_its_limit_does_not_spend_the_service_budget(db_session, monkeypatch):
    monkeypatch.setenv("CAR_VOICE_DAILY_MAX", "1")
    monkeypatch.setenv("CAR_VOICE_SERVICE_DAILY_MAX", "100")
    db_session.query(CarVoiceServiceQuota).delete()
    db_session.commit()
    device = new_device(db_session)
    now = kst(2026, 11, 16, 9)

    spend(db_session, device, now)
    for _ in range(3):
        with pytest.raises(VoiceQuotaExceededError):
            spend(db_session, device, now)

    assert db_session.get(CarVoiceServiceQuota, 1).used_count == 1


def test_ip_limit_is_shared_by_devices_behind_one_ip(db_session, monkeypatch):
    monkeypatch.setenv("CAR_VOICE_IP_DAILY_MAX", "2")
    monkeypatch.setenv("CAR_VOICE_SERVICE_DAILY_MAX", "100")
    db_session.query(CarVoiceServiceQuota).delete()
    db_session.query(CarVoiceIpLimit).delete()
    db_session.commit()
    now = kst(2026, 11, 16, 9)

    spend(db_session, new_device(db_session), now, ip="shared")
    spend(db_session, new_device(db_session), now, ip="shared")
    with pytest.raises(VoiceQuotaExceededError) as caught:
        spend(db_session, new_device(db_session), now, ip="shared")
    spend(db_session, new_device(db_session), now, ip="other")
    spend(db_session, new_device(db_session), kst(2026, 11, 17), ip="shared")

    assert caught.value.scope == "ip"
    assert caught.value.speech == IP_LIMIT_SPEECH
    # IP 한도에 걸린 요청은 서비스 예산을 쓰지 않는다 (2 + other 1 + 다음 날은 새 창).
    assert db_session.get(CarVoiceServiceQuota, 1).used_count == 1
