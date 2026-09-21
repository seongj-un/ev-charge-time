from evcharge.infra.security import (
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)


def test_hash_password_differs_from_plaintext_and_is_salted():
    hashed1 = hash_password("password123")
    hashed2 = hash_password("password123")

    assert hashed1 != "password123"
    assert hashed1 != hashed2  # 같은 평문도 솔트 때문에 매번 다른 해시가 나온다


def test_verify_password_true_for_correct_false_for_wrong():
    hashed = hash_password("password123")

    assert verify_password("password123", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_hash_token_is_deterministic_and_distinguishes_tokens():
    token = "same-token-value"
    other = "different-token-value"

    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != hash_token(other)


def test_new_session_token_is_long_and_random():
    token1 = new_session_token()
    token2 = new_session_token()

    assert len(token1) >= 32
    assert token1 != token2
