"""F-10 **서비스 전체** 호출 한도 (사용자별 한도와 별개).

사용자별 한도만으로는 공개 서버를 지킬 수 없다. 회원가입이 열려 있으면
계정을 여러 개 만드는 것으로 "사용자당 N회"가 사실상 무제한이 되는데,
무료 티어의 일일 할당량은 **프로젝트 전체**에 걸린다. 한 사람이 공용
예산을 비우면 그날 나머지 모두의 질문이 막힌다.

그래서 두 한도를 함께 건다. 화면이 둘을 다르게 말해야 하므로
``X-RateLimit-Scope`` 헤더로 어느 쪽에 걸렸는지 알린다 — 개인 한도는
기다리면 풀리고, 서비스 한도는 "오늘은 여기까지"에 가깝다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.api.routes.extensions import gemini_api_key, llm_client
from evcharge.domain.pricing import KST
from evcharge.infra.models import ChatServiceQuota, User
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.security import hash_password, hash_token, new_session_token

from .test_chat import FULL_EXTRACTION, QUESTION

SERVICE_LIMIT = 2


class _StaticLlm:
    def generate_json(self, *, system_instruction: str, prompt: str, schema: type) -> str:
        return json.dumps(FULL_EXTRACTION)


def _sign_up(db_session, suffix: str) -> str:
    """진짜 사용자와 세션을 만들고 토큰을 돌려준다."""
    user_id = str(uuid.uuid4())
    token = new_session_token()
    db_session.add(
        User(
            id=user_id,
            email=f"svc-quota-{suffix}-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password("password123"),
        )
    )
    db_session.flush()
    db_session.add(
        SessionModel(
            id=str(uuid.uuid4()),
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=datetime.now(KST) + timedelta(days=14),
        )
    )
    db_session.flush()
    return token


@pytest.fixture
def chat_ready(client, db_session, monkeypatch):
    """서비스 한도만 낮게 켜고, 사용자별 한도는 넉넉히 둔다.

    사용자별 한도가 먼저 걸리면 이 파일이 검증하려는 것을 못 본다.
    """
    monkeypatch.setenv("CHAT_SERVICE_LIMIT_COUNT", str(SERVICE_LIMIT))
    monkeypatch.setenv("CHAT_SERVICE_LIMIT_WINDOW_HOURS", "24")
    monkeypatch.setenv("CHAT_RATE_LIMIT_COUNT", "999")

    client.app.dependency_overrides[gemini_api_key] = lambda: "test-key"
    client.app.dependency_overrides[llm_client] = _StaticLlm
    # 행 하나짜리 카운터라 앞선 테스트가 남긴 값이 그대로 보인다.
    db_session.query(ChatServiceQuota).delete()
    db_session.flush()
    return client


def _ask(client, token):
    client.cookies.set(SESSION_COOKIE, token)
    return client.post("/api/chat", json={"message": QUESTION})


def test_the_service_limit_is_shared_across_different_users(chat_ready, db_session):
    """**계정을 바꿔도 예산은 하나다.** 이 테스트가 이 기능의 존재 이유다."""
    first = _sign_up(db_session, "a")
    second = _sign_up(db_session, "b")

    assert _ask(chat_ready, first).status_code == 200
    assert _ask(chat_ready, second).status_code == 200

    # 세 번째는 또 다른 새 계정이다 — 개인 한도는 999라 남아돈다.
    third = _sign_up(db_session, "c")
    blocked = _ask(chat_ready, third)

    assert blocked.status_code == 429, (
        "새 계정으로 서비스 전체 한도를 넘겼다. 사용자별 한도만 있으면 "
        "가입을 반복하는 것으로 무료 티어 예산을 전부 빼낼 수 있다."
    )


def test_the_refusal_says_which_limit_was_hit(chat_ready, db_session):
    """화면이 둘을 다르게 말할 수 있어야 한다.

    개인 한도는 기다리면 풀리고, 서비스 한도는 그날 안에는 안 풀린다.
    같은 429에 같은 문구를 주면 사용자는 몇 분 뒤 다시 눌러 보고 또 막힌다.
    """
    token = _sign_up(chat_ready and db_session, "scope")
    for _ in range(SERVICE_LIMIT):
        assert _ask(chat_ready, token).status_code == 200

    blocked = _ask(chat_ready, token)

    assert blocked.status_code == 429
    assert blocked.headers.get("X-RateLimit-Scope") == "service"
    assert blocked.headers.get("Retry-After") is not None
    # 남은 기능까지 막힌 것으로 오해하지 않게 한다.
    assert "추천" in blocked.json()["detail"]


def test_zero_means_no_service_limit(client, db_session, monkeypatch):
    """0은 "한도 없음"이다 — 개발·테스트에서 이 카운터를 통째로 끄는 스위치."""
    monkeypatch.setenv("CHAT_SERVICE_LIMIT_COUNT", "0")
    monkeypatch.setenv("CHAT_RATE_LIMIT_COUNT", "999")
    client.app.dependency_overrides[gemini_api_key] = lambda: "test-key"
    client.app.dependency_overrides[llm_client] = _StaticLlm
    db_session.query(ChatServiceQuota).delete()
    db_session.flush()

    token = _sign_up(db_session, "off")
    for _ in range(SERVICE_LIMIT + 3):
        assert _ask(client, token).status_code == 200

    assert db_session.query(ChatServiceQuota).count() == 0, (
        "한도를 끄면 카운터 행도 만들지 않는다 — 쓰지 않는 값을 쌓아 두면 "
        "나중에 켰을 때 이미 소진된 상태로 시작한다."
    )
