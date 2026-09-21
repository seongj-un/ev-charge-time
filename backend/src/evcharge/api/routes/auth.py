from fastapi import APIRouter, Response

from ..schemas import LoginRequest, SignupRequest, UserOut
from ._stub import not_implemented

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(payload: SignupRequest):
    """F-11 회원가입. 성공 시 httpOnly 쿠키 발급 (자동 로그인)."""
    return not_implemented("회원가입")()


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest):
    """F-11 로그인. 실패 메시지는 가입 여부를 노출하지 않도록 통일한다."""
    return not_implemented("로그인")()


@router.post("/logout", status_code=204)
def logout(response: Response):
    """F-11 로그아웃. 쿠키 삭제."""
    return not_implemented("로그아웃")()
