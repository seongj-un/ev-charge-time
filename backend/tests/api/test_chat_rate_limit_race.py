"""F-10 호출 제한이 **병렬 요청으로 우회되지 않는지** (``test_login_lockout_race.py``와 같은 함정).

로그인 잠금 카운터가 정확히 이 버그를 갖고 있었다: ``failed_count += 1``을
파이썬에서 읽고-쓰기로 처리해서, ``get_session()``이 요청마다 새 커넥션을 여는
구조(기본 READ COMMITTED)에서는 병렬 요청들이 같은 값을 읽고 같은 값을 덮어써
증가분이 사라졌다(lost update). 순차 5회는 잠기는데 병렬 5회는 안 잠겼다.

호출 제한에서 같은 일이 벌어지면 결과가 더 나쁘다 — 잠금은 늦게 걸릴 뿐이지만,
호출 제한이 새면 무료 티어의 공용 할당량이 그대로 빠져나가 그 뒤의 모든
사용자가 답을 못 받는다.

``client``/``db_session`` 픽스처는 테스트 하나당 커넥션 하나를 SAVEPOINT로 감싸
공유하는 구조라 진짜 경합을 만들 수 없다. 그래서 ``concurrent`` 픽스처(A-3)를
쓴다 — ``get_session`` 오버라이드가 없는 진짜 앱에 여러 OS 스레드로 동시에
요청을 보내, 프로덕션과 똑같이 요청마다 새 커넥션을 타게 한다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.api.routes.extensions import gemini_api_key, llm_client
from evcharge.domain.pricing import KST
from evcharge.infra.models import ChatRateLimit, User
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.security import hash_password, hash_token, new_session_token

from .test_chat import FULL_EXTRACTION, QUESTION

LIMIT = 3
# 제한보다 넉넉히 더 보낸다. 카운터가 원자적이지 않으면 초과분 중 일부가
# 200으로 새어 나온다.
CONCURRENCY = LIMIT + 4


class _StaticLlm:
    """스레드에서 공유되는 가짜 LLM. 상태가 없어 락이 필요 없다."""

    def generate_json(self, *, system_instruction: str, prompt: str, schema: type) -> str:
        return json.dumps(FULL_EXTRACTION)


def test_the_quota_is_not_bypassable_by_parallel_requests(concurrent, monkeypatch):
    monkeypatch.setenv("CHAT_RATE_LIMIT_COUNT", str(LIMIT))
    # 창이 넘어가는 순간에 테스트가 걸리면 카운터가 초기화되어 기대값이 흔들린다.
    # 창을 하루로 늘려 그 가능성을 없앤다 — 검증 대상은 창 경계가 아니라 원자성이다.
    monkeypatch.setenv("CHAT_RATE_LIMIT_WINDOW_MINUTES", str(24 * 60))

    concurrent.app.dependency_overrides[gemini_api_key] = lambda: "test-key"
    concurrent.app.dependency_overrides[llm_client] = _StaticLlm

    user_id = str(uuid.uuid4())
    email = f"chat-race-{uuid.uuid4().hex}@example.com"
    token = new_session_token()

    # 진짜 커넥션으로 직접 커밋한다. 동시에 열리는 요청들의 세션과 이 세션이
    # 서로 다른 진짜 트랜잭션이어야 경합이 재현된다.
    setup_session = concurrent.session()
    try:
        setup_session.add(
            User(id=user_id, email=email, password_hash=hash_password("password123"))
        )
        setup_session.commit()
        setup_session.add(
            SessionModel(
                id=str(uuid.uuid4()),
                user_id=user_id,
                token_hash=hash_token(token),
                expires_at=datetime.now(KST) + timedelta(days=14),
            )
        )
        setup_session.commit()
    finally:
        setup_session.close()

    def ask(client):
        client.cookies.set(SESSION_COOKIE, token)
        return client.post("/api/chat", json={"message": QUESTION}).status_code

    try:
        results = concurrent.run(ask, count=CONCURRENCY)

        allowed = results.count(200)
        rejected = results.count(429)

        assert allowed + rejected == CONCURRENCY, (
            f"200도 429도 아닌 응답이 섞였다: {sorted(results)}"
        )
        assert allowed == LIMIT, (
            f"동시 요청 {CONCURRENCY}건 중 {allowed}건이 통과했다 (제한은 {LIMIT}). "
            "카운터 증가가 원자적이지 않으면(읽고-쓰기) 병렬 요청들이 같은 값을 "
            "읽어 증가분을 잃어버리고, 제한을 넘긴 요청까지 200을 받는다 — "
            "login_attempts.failed_count에 있던 바로 그 버그다."
        )

        verify_session = concurrent.session()
        try:
            row = verify_session.get(ChatRateLimit, user_id)
        finally:
            verify_session.close()

        assert row is not None
        assert row.used_count == CONCURRENCY, (
            f"동시 요청 {CONCURRENCY}건을 보냈는데 최종 used_count={row.used_count}. "
            "거절된 요청도 카운터는 올라가야 한다 — 그래야 계속 두드려서 "
            "창이 끝나기 전에 예산을 다시 얻어내는 일이 없다."
        )
    finally:
        cleanup_session = concurrent.session()
        try:
            # users.id를 ondelete CASCADE로 물려 뒀으므로 sessions·chat_rate_limits도
            # 함께 지워진다 (bulk delete는 DB의 FK 캐스케이드를 그대로 탄다).
            cleanup_session.query(User).filter_by(id=user_id).delete()
            cleanup_session.commit()
        finally:
            cleanup_session.close()
