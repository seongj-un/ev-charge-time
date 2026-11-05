"""비밀번호 실패 잠금. 로그인과 탈퇴 재확인이 같은 이메일 카운터를 쓴다.

탈퇴의 비밀번호 재확인이 따로 놀면, 남의 세션을 쥔 사람이 거기서 비밀번호를
무제한으로 맞혀 볼 수 있다 — 로그인 5회 잠금이 그 한 곳에서 새는 셈이다.
"""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from ..infra.models import LoginAttempt
from ..settings import get_settings

# 로그인·탈퇴 두 곳에서 뜨므로 "로그인"이라고 쓰지 않는다.
LOCKED_MESSAGE = "비밀번호를 여러 번 틀려서 잠겼어요. 잠시 후 다시 시도해 주세요."


def raise_if_locked(db: DbSession, email: str, now: datetime) -> None:
    attempt = db.get(LoginAttempt, email)
    if attempt is not None and attempt.locked_until is not None and attempt.locked_until > now:
        raise HTTPException(status_code=429, detail=LOCKED_MESSAGE)


def record_failure(db: DbSession, email: str, now: datetime) -> None:
    """실패 1회를 원자적으로 센다. 한도에 닿으면 잠근다. 커밋까지 한다.

    failed_count += 1을 애플리케이션에서 읽고-쓰면(READ COMMITTED, 요청마다
    새 커넥션) 병렬 요청들이 같은 값을 읽어 같은 값을 덮어써 증가분을 잃어버린다
    (lost update) — 순차 5회는 잠기는데 병렬 5회는 안 잠기는 원인이었다.
    INSERT ... ON CONFLICT DO UPDATE SET failed_count = failed_count + 1은
    Postgres가 대상 행에 잠금을 걸고 동시 요청을 직렬화해 처리하므로,
    애플리케이션 코드가 값을 보지 않고도 원자적으로 +1이 반영된다.
    """
    settings = get_settings()
    increment_stmt = (
        pg_insert(LoginAttempt)
        .values(email=email, failed_count=1)
        .on_conflict_do_update(
            index_elements=[LoginAttempt.email],
            set_={"failed_count": LoginAttempt.failed_count + 1},
        )
        .returning(LoginAttempt.failed_count)
    )
    failed_count = db.execute(increment_stmt).scalar_one()
    if failed_count >= settings.login_max_attempts:
        db.execute(
            update(LoginAttempt)
            .where(LoginAttempt.email == email)
            .values(locked_until=now + timedelta(minutes=settings.login_lockout_minutes))
        )
    db.commit()
