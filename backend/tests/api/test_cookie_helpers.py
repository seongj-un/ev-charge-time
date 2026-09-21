"""Finding 4 회귀 테스트: set_session_cookie/clear_session_cookie가 실제로 굽는
Set-Cookie 헤더 속성을 검증한다.

지금까지 아무도 httponly·samesite·secure(설정값)·path·max_age를 실제 응답
헤더에서 확인하지 않았다 — secure=True를 하드코딩하거나 samesite 오타가 나도
조용히 배포될 수 있었다는 뜻이다. DB를 전혀 쓰지 않는 최소 앱으로 헬퍼를 직접
붙여서, Postgres 유무와 무관하게(Finding 5) 항상 돈다.
"""

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from evcharge.api.auth_deps import SESSION_COOKIE, clear_session_cookie, set_session_cookie
from evcharge.settings import get_settings


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/set")
    def _set(response: Response):
        set_session_cookie(response, "raw-token-value")
        return {}

    @app.get("/clear")
    def _clear(response: Response):
        clear_session_cookie(response)
        return {}

    return app


def _cookie_header(response) -> str:
    header = response.headers.get("set-cookie")
    assert header, "Set-Cookie 헤더가 없다"
    return header


def test_set_session_cookie_has_httponly_samesite_path_and_max_age():
    client = TestClient(_make_app())
    settings = get_settings()

    response = client.get("/set")

    header = _cookie_header(response).lower()
    assert header.startswith(f"{SESSION_COOKIE}=")
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/" in header
    assert f"max-age={settings.session_days * 24 * 60 * 60}" in header


def test_set_session_cookie_secure_flag_matches_settings():
    client = TestClient(_make_app())
    settings = get_settings()

    response = client.get("/set")

    header = _cookie_header(response).lower()
    # secure=True가 실수로 하드코딩되거나, 반대로 settings.cookie_secure=True인데
    # 빠지는 걸 잡기 위해 설정값과 정확히 일치하는지 본다(둘 다 아니라 "and" 조건).
    assert ("secure" in header) == settings.cookie_secure


def test_clear_session_cookie_expires_the_cookie_immediately():
    client = TestClient(_make_app())

    response = client.get("/clear")

    header = _cookie_header(response).lower()
    assert header.startswith(f"{SESSION_COOKIE}=")
    assert "path=/" in header
    # Starlette의 delete_cookie는 값 없이 Max-Age=0(과거 만료)로 즉시 지운다.
    assert "max-age=0" in header
