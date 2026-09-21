"""세션 쿠키 읽기/쓰기와 로그인 사용자 의존성.

세션은 서버 쪽 DB 테이블(``infra.models.Session``)로 관리한다. 쿠키에는
토큰 원본만 담고, DB 조회는 그 토큰의 sha256 해시(``infra.security.hash_token``)로
한다 — 로그아웃·탈퇴가 즉시 반영되도록 하기 위한 선택 (JWT 대신 서버 세션).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..domain.pricing import KST
from ..infra.db import get_session
from ..infra.models import Session as SessionModel
from ..infra.models import User
from ..infra.security import hash_token
from ..settings import get_settings

SESSION_COOKIE = "session"


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="로그인이 필요합니다.")


def current_user(
    request: Request, session: DbSession = Depends(get_session)
) -> User:
    """세션 쿠키로 로그인한 사용자를 찾는다. 없거나·잘못됐거나·만료면 401."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthorized()

    db_session_row = session.scalar(
        select(SessionModel).where(SessionModel.token_hash == hash_token(token))
    )
    if db_session_row is None:
        raise _unauthorized()

    if db_session_row.expires_at < datetime.now(KST):
        raise _unauthorized()

    user = session.get(User, db_session_row.user_id)
    if user is None:
        raise _unauthorized()

    return user


def set_session_cookie(response: Response, token: str) -> None:
    """로그인·회원가입 성공 시 세션 쿠키를 굽는다."""
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.session_days * 24 * 60 * 60,
    )


def clear_session_cookie(response: Response) -> None:
    """로그아웃 시 세션 쿠키를 지운다. DB의 세션 행 삭제는 호출자 책임."""
    response.delete_cookie(key=SESSION_COOKIE, path="/")
