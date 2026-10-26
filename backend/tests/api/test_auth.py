"""F-11 회원가입·로그인·로그아웃·내 정보·탈퇴.

실패 메시지가 이메일 존재 여부를 노출하면 안 되므로, 틀린 비밀번호와 없는
이메일은 상태코드·본문이 완전히 같아야 한다 (API 명세서 3장).
"""

import statistics
import time
import uuid

import pytest

from evcharge.settings import get_settings

EMAIL = "signup-flow@example.com"
PASSWORD = "correct-horse-battery"


def signup(client, *, email=EMAIL, password=PASSWORD, nickname="충전러"):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "nickname": nickname},
    )


def login(client, *, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_signup_returns_201_hides_password_sets_cookie_and_logs_in(client):
    response = signup(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert body["nickname"] == "충전러"
    assert body.get("id")
    assert "password" not in body
    assert "password_hash" not in body
    assert PASSWORD not in response.text

    assert "session" in response.cookies
    assert body["created_at"].endswith("+09:00")

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL
    assert me.json()["created_at"].endswith("+09:00")


def test_duplicate_email_signup_is_409(client):
    assert signup(client, email="dup@example.com").status_code == 201

    response = signup(client, email="dup@example.com")

    assert response.status_code == 409


def test_short_password_is_422(client):
    response = signup(client, email="short-pw@example.com", password="1234567")

    assert response.status_code == 422


def test_login_success_returns_200_and_sets_cookie(client):
    signup(client, email="login-ok@example.com")
    client.cookies.clear()

    response = login(client, email="login-ok@example.com")

    assert response.status_code == 200
    assert response.json()["email"] == "login-ok@example.com"
    assert "session" in response.cookies


def test_wrong_password_and_unknown_email_give_identical_401(client):
    signup(client, email="login-wrong-pw@example.com")
    client.cookies.clear()

    wrong_password = login(
        client, email="login-wrong-pw@example.com", password="not-the-password"
    )
    unknown_email = login(
        client, email="nobody-registered@example.com", password="whatever123"
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["detail"] == "이메일 또는 비밀번호가 올바르지 않습니다"


def test_five_failures_lock_the_sixth_attempt_even_with_correct_password(client):
    email = "lockout@example.com"
    signup(client, email=email)
    client.cookies.clear()
    settings = get_settings()

    for _ in range(settings.login_max_attempts):
        response = login(client, email=email, password="wrong-password")
        assert response.status_code == 401

    locked = login(client, email=email, password=PASSWORD)

    assert locked.status_code == 429


def test_successful_login_resets_the_failure_counter(client):
    email = "reset-counter@example.com"
    signup(client, email=email)
    client.cookies.clear()

    for _ in range(3):
        assert login(client, email=email, password="wrong-password").status_code == 401

    assert login(client, email=email, password=PASSWORD).status_code == 200
    client.cookies.clear()

    # 리셋되지 않았다면 이 3번 중에 실패 누적이 5에 도달해 429가 튀어나왔을 것.
    for _ in range(3):
        assert login(client, email=email, password="wrong-password").status_code == 401


def test_logout_deletes_session_so_cookie_no_longer_works(client):
    signup(client, email="logout@example.com")

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 204

    me = client.get("/api/me")
    assert me.status_code == 401


def test_logout_requires_login(client):
    response = client.post("/api/auth/logout")
    assert response.status_code == 401


def test_me_without_cookie_is_401(client):
    response = client.get("/api/me")
    assert response.status_code == 401


def test_delete_account_wrong_password_is_401(client):
    signup(client, email="delete-wrong@example.com")

    response = client.request(
        "DELETE", "/api/me", json={"password": "not-the-password"}
    )

    assert response.status_code == 401


def test_delete_account_success_frees_the_email_for_reuse(client):
    email = "delete-ok@example.com"
    signup(client, email=email)

    response = client.request("DELETE", "/api/me", json={"password": PASSWORD})
    assert response.status_code == 204

    again = signup(client, email=email)
    assert again.status_code == 201


def test_logout_response_actually_clears_the_session_cookie(client):
    """Finding 2 회귀 테스트.

    ``logout``이 ``clear_session_cookie(response)``로 주입된 ``response``에
    삭제 헤더를 단 뒤 ``return Response(status_code=204)``로 **새** Response를
    반환하면, FastAPI가 그 새 객체를 쓰면서 주입된 ``response``에 달아둔
    Set-Cookie 헤더를 버린다 — 세션 행은 지워져도 브라우저에는 죽은 쿠키가
    계속 남는다. ``test_cookie_helpers.py``는 헬퍼를 합성 앱에 직접 붙여서
    검증하므로 이 결함을 잡지 못한다 — 반드시 실제 라우터를 통해야 한다.
    """
    signup(client, email="logout-cookie@example.com")

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    header = response.headers.get("set-cookie", "").lower()
    assert header, "logout 응답에 Set-Cookie 헤더가 없다"
    assert "session=" in header
    assert "max-age=0" in header


def test_delete_account_response_actually_clears_the_session_cookie(client):
    """Finding 2 회귀 테스트. ``DELETE /api/me``도 로그아웃과 같은 패턴으로
    쿠키 삭제 헤더를 잃는다."""
    email = "delete-cookie@example.com"
    signup(client, email=email)

    response = client.request("DELETE", "/api/me", json={"password": PASSWORD})

    assert response.status_code == 204
    header = response.headers.get("set-cookie", "").lower()
    assert header, "탈퇴 응답에 Set-Cookie 헤더가 없다"
    assert "session=" in header
    assert "max-age=0" in header


# ── I-2: DB 컬럼 길이 초과가 500으로 새면 안 된다 ───────────────────────────
#
# 리뷰어가 라이브로 재현: nickname 60자(컬럼은 varchar(50)), email 406자
# (컬럼은 varchar(320))가 스키마의 max_length 부재로 그대로 DB까지 내려가
# StringDataRightTruncation → sqlalchemy.exc.DataError → 500이 됐다. 둘 다
# 로그인이 필요 없는 회원가입 경로라 누구나 칠 수 있었다.


def test_signup_nickname_over_column_length_is_422(client):
    response = signup(client, email="long-nickname@example.com", nickname="n" * 60)
    assert response.status_code == 422


def test_signup_email_over_column_length_is_422(client):
    long_email = ("a" * 390) + "@example.com"
    response = signup(client, email=long_email)
    assert response.status_code == 422


# ── I-3: 이메일 정규화·검증 ─────────────────────────────────────────────
#
# 리뷰어 실측: ``Mixed@Example.COM``으로 가입한 뒤 ``mixed@example.com``으로
# 또 가입하면 둘 다 201(계정이 두 개가 되어, 다음 로그인이 빈 계정에 붙는다).
# ``""``·``"not-an-email"``도 그대로 가입됐다. 기능 명세 F-11이 "검증: 이메일
# 형식"을 요구한다.


def test_signup_email_case_variant_of_existing_account_is_409(client):
    assert signup(client, email="Mixed4c1bed@Example.COM").status_code == 201

    response = signup(client, email="mixed4c1bed@example.com")

    assert response.status_code == 409


def test_signup_uppercase_then_login_lowercase_succeeds(client):
    """대문자로 가입해도(iOS 자동 대문자 등) 소문자로 로그인되어야 한다 —
    저장·조회 양쪽이 같은 정규화를 거쳐야 새 빈 계정이 생기지 않는다."""
    signup(client, email="Upper4c1bed@Example.COM", password="password123")
    client.cookies.clear()

    response = login(client, email="upper4c1bed@example.com", password="password123")

    assert response.status_code == 200
    assert response.json()["email"] == "upper4c1bed@example.com"


def test_signup_invalid_email_format_is_422(client):
    response = signup(client, email="not-an-email")
    assert response.status_code == 422


def test_signup_empty_email_is_422(client):
    response = signup(client, email="")
    assert response.status_code == 422


def test_login_timing_does_not_leak_whether_the_email_is_registered(client):
    """Finding 1 회귀 테스트 (Critical).

    고치기 전 코드는 ``user is None or not verify_password(...)``가 단락 평가돼
    가입되지 않은 이메일이면 Argon2 검증을 통째로 건너뛰었다. 리뷰어 실측으로
    검증 경로(~30ms) vs 스킵 경로(~0.0001ms)가 약 25만 배 차이났다 — 상태
    코드·본문이 같아도 응답 시간만 재면 가입 여부를 열거할 수 있었다는 뜻이다.

    표본 하나로는 시스템 노이즈에 흔들리므로 여러 표본을 뽑아 중앙값을 비교한다.
    표본마다 새 계정/새 이메일을 쓰는 이유: 같은 계정에 반복해서 틀린 비밀번호를
    보내면 5회째부터 잠금(429)으로 분기가 바뀌어 verify_password 자체를 다시
    스킵하게 되므로, 측정하려는 신호가 오염된다.

    HTTP 왕복 전체를 재므로 DB 조회·TestClient 오버헤드가 두 경로 모두에 깔리는
    바닥값으로 깔린다 — 그래서 실측 배율은 raw verify_password 단독 비교(~25만
    배)보다 작다. 실측(이 저장소 기준): 고치기 전 중앙값 비율 ~9배(등록된
    이메일 ~37ms vs 미등록 ~4ms), 고친 뒤 ~1배(둘 다 인자 해시 비용에 지배됨).
    임계값(3배)은 그 사이 넉넉한 자리에 잡아서, 버그는 확실히 잡되 정상 지터에는
    흔들리지 않게 했다.
    """
    samples = 10
    registered_times: list[float] = []
    unknown_times: list[float] = []

    for i in range(samples):
        email = f"timing-registered-{i}-{uuid.uuid4().hex[:8]}@example.com"
        signup(client, email=email)
        client.cookies.clear()

        start = time.perf_counter()
        response = login(client, email=email, password="totally-wrong-password")
        registered_times.append(time.perf_counter() - start)
        assert response.status_code == 401

        client.cookies.clear()

    for i in range(samples):
        email = f"timing-unknown-{i}-{uuid.uuid4().hex[:8]}@example.com"

        start = time.perf_counter()
        response = login(client, email=email, password="whatever-password")
        unknown_times.append(time.perf_counter() - start)
        assert response.status_code == 401

    median_registered = statistics.median(registered_times)
    median_unknown = statistics.median(unknown_times)

    slower = max(median_registered, median_unknown)
    faster = max(min(median_registered, median_unknown), 1e-9)
    ratio = slower / faster

    assert ratio < 3, (
        "로그인 응답 시간이 자릿수 단위로 벌어졌다 — 가입 여부가 타이밍으로 샌다 "
        f"(registered={median_registered * 1000:.3f}ms, "
        f"unknown={median_unknown * 1000:.3f}ms, ratio={ratio:.1f}x)"
    )


# 이메일 정규화(strip·lower)가 타입 검증보다 먼저 돈다. 문자열이 아닌 값이 오면
# .strip()에서 AttributeError가 나 500이 됐다 — 형식이 틀린 요청은 422여야 한다.
@pytest.mark.parametrize("path", ["/api/auth/signup", "/api/auth/login"])
@pytest.mark.parametrize("email", [None, 123, ["a@example.com"], {"x": 1}, True])
def test_a_non_string_email_is_422_not_500(client, path, email):
    body = {"email": email, "password": "password123", "nickname": "테스터"}

    response = client.post(path, json=body)

    assert response.status_code == 422
