from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session as DbSession

from ...domain.pricing import KST
from ...infra.db import get_session
from ...infra.models import User
from ...infra.security import verify_password
from ..auth_deps import clear_session_cookie, current_user
from ..login_lockout import raise_if_locked, record_failure
from ..schemas import DeleteAccountRequest, UserOut

router = APIRouter(prefix="/api/me", tags=["me"])

# 모두 로그인 필요. 본인 데이터만 접근하며 다른 사용자 리소스 ID는 404.


@router.get("", response_model=UserOut)
def read_me(user: User = Depends(current_user)):
    return user


@router.delete("", status_code=204)
def delete_me(
    payload: DeleteAccountRequest,
    response: Response,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_session),
):
    """F-11 탈퇴. 비밀번호로 재확인한다. 차량·충전 기록·즐겨찾기·세션은 DB 쪽
    ON DELETE CASCADE로 함께 삭제된다 (infra/models.py)."""
    # 재확인도 로그인과 같은 실패 카운터를 쓴다 — 세션만 쥐면 여기서 비밀번호를
    # 무제한으로 맞혀 볼 수 있었다 (login_lockout.py).
    now = datetime.now(KST)
    raise_if_locked(db, user.email, now)
    if not verify_password(payload.password, user.password_hash):
        record_failure(db, user.email, now)
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")

    db.delete(user)
    db.commit()
    clear_session_cookie(response)
    # (Finding 2) auth.logout과 같은 결함: 새 Response(status_code=204)를
    # 반환하면 FastAPI가 주입된 `response`의 Set-Cookie 헤더를 버린다.
    # 데코레이터가 이미 status_code=204를 정하므로 None을 반환한다.
    return


# /api/me/* 의 나머지는 기능별로 분리되어 있다:
#   내 차량(F-12)        → routes/me_vehicles.py
#   충전 기록(F-13)      → routes/me_plans.py
#   즐겨찾는 충전소(F-14) → routes/me_favorites.py
