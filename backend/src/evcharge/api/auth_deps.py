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


def _session_user(request: Request, session: DbSession) -> User | None:
    """세션 쿠키가 가리키는 사용자. 없거나·잘못됐거나·만료면 None."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    db_session_row = session.scalar(
        select(SessionModel).where(SessionModel.token_hash == hash_token(token))
    )
    if db_session_row is None:
        return None

    if db_session_row.expires_at < datetime.now(KST):
        return None

    return session.get(User, db_session_row.user_id)


def current_user(
    request: Request, session: DbSession = Depends(get_session)
) -> User:
    """세션 쿠키로 로그인한 사용자를 찾는다. 없거나·잘못됐거나·만료면 401."""
    user = _session_user(request, session)
    if user is None:
        raise _unauthorized()
    return user


def optional_user(
    request: Request, session: DbSession = Depends(get_session)
) -> User | None:
    """로그인했으면 사용자, 게스트면 None. **401을 던지지 않는다.**

    게스트도 볼 수 있지만 로그인하면 내용이 달라지는 엔드포인트용이다 — F-07
    주변 충전소의 ``is_favorite``은 로그인 시 true/false, 게스트는 null이다
    (명세 2-4). ``current_user``를 쓰면 게스트가 401로 튕겨 목록 자체를 못 본다.
    """
    return _session_user(request, session)


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
