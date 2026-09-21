"""비밀번호 해시(Argon2id)와 세션 토큰 생성·해시.

세션 토큰 원본은 DB에 저장하지 않는다. `hash_token`으로 만든 sha256 값만
저장해서, DB가 유출되더라도 토큰을 되살려 세션을 탈취할 수 없게 한다.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher

_hasher = PasswordHasher()


def hash_password(raw: str) -> str:
    """평문 비밀번호를 Argon2id로 해시한다. 호출마다 솔트가 달라 결과도 매번 다르다."""
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    """평문이 저장된 해시와 일치하면 True. 형식이 잘못된 해시도 예외 없이 False."""
    try:
        return _hasher.verify(hashed, raw)
    except Exception:
        return False


def new_session_token() -> str:
    """세션 쿠키에 담을 무작위 토큰. 32바이트 엔트로피, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """세션 토큰을 DB 저장용 sha256 해시로 바꾼다. 같은 토큰은 항상 같은 값."""
    return hashlib.sha256(token.encode()).hexdigest()
