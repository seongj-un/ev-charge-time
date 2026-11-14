"""와트잇 차량 앱 기기 토큰과 기기 발급 속도 제한 (BE-5).

차량 앱은 로그인이 없다. ``POST /api/car/devices``가 기기 하나에 무작위 토큰을
발급하고(응답에 한 번만), 서버는 그 sha256만 저장한다(세션 토큰과 같은 방식,
``infra/security.py``). 이후 요청은 ``Authorization: Bearer <토큰>``으로 기기를 밝힌다.

- 절감 기록이 필요한 엔드포인트(``confirm``, ``summary``)는 토큰이 없거나 틀리면 401.
- 계산 엔드포인트(``car/plan``, ``car/leak-check``)는 토큰이 없거나 틀려도 계산은
  그대로 돌려준다. 기록만 하지 않는다 (편의 우선: 계산 실패 금지).

기기 발급은 공개 엔드포인트라 IP별 고정 창 제한을 건다. ``chat`` 한도와 같은 UPSERT
한 문장 카운터이고, IP 원문 대신 가명 처리한 키(``ip_key``)를 쓴다.

운영에서는 Caddy가 앞에 있어 ``request.client.host``가 Caddy 컨테이너 주소가 된다.
uvicorn이 Caddy의 ``X-Forwarded-For``를 믿도록 ``FORWARDED_ALLOW_IPS``를 준다
(``docker-compose.prod.yml``). Caddy는 ``trusted_proxies``를 두지 않으면 클라이언트가
보낸 ``X-Forwarded-For``를 믿지 않고 실제 접속 주소로 채운다.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta
from math import ceil

from fastapi import HTTPException, Request
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from ..domain.pricing import KST
from ..infra.models import CarDevice, CarDeviceRateLimit
from ..infra.security import hash_token, new_session_token
from ..settings import get_settings

logger = logging.getLogger(__name__)
_warned_without_secret = False

# 토큰은 new_session_token()이 만드는 43자다. 그보다 훨씬 긴 값은 해시하지 않고 버린다.
MAX_TOKEN_LENGTH = 256


def issue_device(session: DbSession) -> tuple[str, str]:
    """새 기기를 만들고 ``(device_id, 토큰 원본)``을 돌려준다. 원본은 저장하지 않는다."""
    token = new_session_token()
    device = CarDevice(id=str(uuid.uuid4()), token_hash=hash_token(token))
    session.add(device)
    session.commit()
    return device.id, token


def bearer_token(request: Request) -> str | None:
    """``Authorization: Bearer <토큰>``의 토큰. 없거나 모양이 다르면 None."""
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    token = value.strip()
    if scheme.lower() != "bearer" or not token or len(token) > MAX_TOKEN_LENGTH:
        return None
    return token


def find_device(session: DbSession, token: str) -> CarDevice | None:
    """토큰에 맞는 기기. 찾으면 ``last_seen_at``을 지금으로 바꾼다(커밋은 호출자)."""
    device = session.scalar(select(CarDevice).where(CarDevice.token_hash == hash_token(token)))
    if device is not None:
        device.last_seen_at = datetime.now(KST)
    return device


def require_device(request: Request, session: DbSession) -> CarDevice:
    """기기 토큰이 꼭 필요한 엔드포인트용. 없거나 틀리면 401."""
    token = bearer_token(request)
    device = find_device(session, token) if token is not None else None
    if device is None:
        raise HTTPException(
            status_code=401,
            detail="기기 토큰이 없거나 올바르지 않습니다. POST /api/car/devices로 발급받으세요.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return device


def client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def ip_key(ip: str) -> str:
    """기기 발급 한도의 키. IP 원문 대신 저장하는 가명 처리 값이다.

    ``CAR_IP_HASH_SECRET``이 있으면 HMAC-SHA256이라 비밀값 없이는 IP를 되찾을 수 없다.
    없으면 sha256인데, IPv4는 대입으로 되찾을 수 있으므로 경고를 한 번 남긴다.
    """
    global _warned_without_secret
    secret = get_settings().car_ip_hash_secret
    if secret:
        return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()
    if not _warned_without_secret:
        _warned_without_secret = True
        logger.warning(
            "CAR_IP_HASH_SECRET이 비어 있어 기기 발급 한도의 IP 키를 솔트 없는 sha256으로 "
            "만듭니다. 운영에서는 비밀값을 설정하세요."
        )
    return hashlib.sha256(ip.encode()).hexdigest()


def consume_device_quota(session: DbSession, ip: str, now: datetime) -> None:
    """이 IP의 이번 창 발급 횟수를 원자적으로 1 늘리고, 넘었으면 429.

    읽고-쓰기 대신 UPSERT 한 문장이라 병렬 요청에도 증가분을 잃지 않는다
    (``extensions._consume_quota``와 같은 방식). 거절된 시도도 센다.
    """
    settings = get_settings()
    window = timedelta(minutes=settings.car_device_rate_limit_window_minutes)
    epoch = datetime(1970, 1, 1, tzinfo=KST)
    window_start = epoch + (now - epoch) // window * window
    ip_hash = ip_key(ip)

    increment = (
        pg_insert(CarDeviceRateLimit)
        .values(ip_hash=ip_hash, window_start=window_start, used_count=1)
        .on_conflict_do_update(
            index_elements=[CarDeviceRateLimit.ip_hash],
            set_={
                "used_count": case(
                    (
                        CarDeviceRateLimit.window_start == window_start,
                        CarDeviceRateLimit.used_count + 1,
                    ),
                    else_=1,
                ),
                "window_start": window_start,
            },
        )
        .returning(CarDeviceRateLimit.used_count)
    )
    used = session.execute(increment).scalar_one()
    session.commit()

    if used > settings.car_device_rate_limit_count:
        retry_after = max(1, ceil((window_start + window - now).total_seconds()))
        raise HTTPException(
            status_code=429,
            detail="기기 등록 요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(retry_after)},
        )
