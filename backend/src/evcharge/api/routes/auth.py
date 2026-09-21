import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
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
    db.commit()

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
    if user is None or not verify_password(payload.password, user.password_hash):
        if attempt is None:
            attempt = LoginAttempt(email=payload.email, failed_count=0)
            db.add(attempt)
        attempt.failed_count += 1
        if attempt.failed_count >= settings.login_max_attempts:
            attempt.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
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
