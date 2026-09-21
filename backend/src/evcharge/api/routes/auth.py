import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ...domain.pricing import KST
from ...infra.db import get_session
from ...infra.models import LoginAttempt, User
from ...infra.models import Session as SessionModel
from ...infra.security import hash_password, hash_token, new_session_token, verify_password
from ...settings import get_settings
from ..auth_deps import SESSION_COOKIE, clear_session_cookie, current_user, set_session_cookie
from ..schemas import LoginRequest, SignupRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOGIN_FAILURE_MESSAGE = "이메일 또는 비밀번호가 올바르지 않습니다"

# 가입되지 않은 이메일로 로그인하면 verify_password를 아예 호출하지 않게 되어
# (user is None 에서 단락 평가) 검증 경로(~30ms)와 스킵 경로(~0.0001ms)의 응답 시간이
# 수만 배 벌어진다 — 응답 시간만 재도 가입 여부를 알아낼 수 있다. 이를 막기 위해
# 사용자가 없을 때도 이 더미 해시를 상대로 항상 verify_password를 호출해 두 경로의
# 비용을 맞춘다. 모듈 로드 시 한 번만 해시를 계산해서 매 요청마다 새로 해시하는
# 비용(그리고 그로 인한 또 다른 타이밍 편차)을 피한다.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-safety-only-never-used")


def _issue_session(db: DbSession, user: User) -> str:
    """새 세션 행을 만들고 쿠키에 담을 원본 토큰을 돌려준다."""
    settings = get_settings()
    token = new_session_token()
    db.add(
        SessionModel(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(KST) + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    return token


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(payload: SignupRequest, response: Response, db: DbSession = Depends(get_session)):
    """F-11 회원가입. 성공 시 httpOnly 쿠키 발급 (자동 로그인)."""
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 위 SELECT와 이 commit 사이에 동시 가입 요청이 먼저 같은 이메일로
        # 커밋하면 unique 제약 위반으로 여기서 걸린다 — 경합에서 진 쪽도 500이
        # 아니라 명세대로 409를 받도록 한다.
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.") from None

    token = _issue_session(db, user)
    set_session_cookie(response, token)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: DbSession = Depends(get_session)):
    """F-11 로그인. 실패 메시지는 가입 여부를 노출하지 않도록 통일한다."""
    settings = get_settings()
    now = datetime.now(KST)

    attempt = db.get(LoginAttempt, payload.email)
    if attempt is not None and attempt.locked_until is not None and attempt.locked_until > now:
        raise HTTPException(
            status_code=429,
            detail="로그인 실패 횟수가 초과되어 잠겼습니다. 잠시 후 다시 시도하세요.",
        )

    user = db.scalar(select(User).where(User.email == payload.email))
    # 가입 여부와 무관하게 항상 verify_password를 호출한다(타이밍 사이드채널 방지,
    # 모듈 상단 주석 참고) — 사용자가 없으면 더미 해시를, 있으면 실제 해시를 검증한다.
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(payload.password, password_hash)

    if user is None or not password_ok:
        # failed_count += 1을 애플리케이션에서 읽고-쓰면(READ COMMITTED, 요청마다
        # 새 커넥션) 병렬 요청들이 같은 값을 읽어 같은 값을 덮어써 증가분을 잃어버린다
        # (lost update) — 순차 5회는 잠기는데 병렬 5회는 안 잠기는 원인이었다.
        # INSERT ... ON CONFLICT DO UPDATE SET failed_count = failed_count + 1은
        # Postgres가 대상 행에 잠금을 걸고 동시 요청을 직렬화해 처리하므로,
        # 애플리케이션 코드가 값을 보지 않고도 원자적으로 +1이 반영된다.
        increment_stmt = (
            pg_insert(LoginAttempt)
            .values(email=payload.email, failed_count=1)
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
                .where(LoginAttempt.email == payload.email)
                .values(locked_until=now + timedelta(minutes=settings.login_lockout_minutes))
            )
        db.commit()
        raise HTTPException(status_code=401, detail=LOGIN_FAILURE_MESSAGE)

    if attempt is not None:
        attempt.failed_count = 0
        attempt.locked_until = None
        db.commit()

    token = _issue_session(db, user)
    set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: DbSession = Depends(get_session),
    _user: User = Depends(current_user),
):
    """F-11 로그아웃. 세션 행을 지우고 쿠키도 지운다. 로그인 필요."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(SessionModel).where(SessionModel.token_hash == hash_token(token)))
        db.commit()
    clear_session_cookie(response)
    return Response(status_code=204)
