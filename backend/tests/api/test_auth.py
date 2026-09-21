"""F-11 회원가입·로그인·로그아웃·내 정보·탈퇴.

실패 메시지가 이메일 존재 여부를 노출하면 안 되므로, 틀린 비밀번호와 없는
이메일은 상태코드·본문이 완전히 같아야 한다 (API 명세서 3장).
"""

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
    assert "id" in body and body["id"]
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
