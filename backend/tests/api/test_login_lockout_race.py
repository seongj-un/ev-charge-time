"""Finding 2 회귀 테스트 (Critical): 로그인 잠금 카운터의 TOCTOU 경쟁.

고치기 전 코드는 ``attempt.failed_count += 1``을 ORM으로 처리했다 — 파이썬이
값을 읽고, +1 하고, 절대값으로 ``UPDATE ... SET failed_count = :new_value``를
커밋하는 식이다. ``get_session()``은 요청마다 새 커넥션/세션을 여니, 기본
READ COMMITTED에서 두 요청이 같은 실패 카운트를 동시에 읽으면 둘 다 같은 +1
결과를 써서 한쪽의 증가분이 사라진다(lost update).

``tests/conftest.py``의 ``db_session``/``client`` 픽스처는 테스트 하나당 커넥션
하나를 SAVEPOINT로 감싸 공유하는 구조라, 진짜 동시 트랜잭션(서로 다른 커넥션이
동시에 같은 행을 읽고 쓰는 상황)을 만들 수 없다. 그래서 이 파일은 그 픽스처를
쓰지 않는다: ``get_session`` 오버라이드가 없는 실제 앱을 만들어서, 요청마다
프로덕션과 똑같이 새 커넥션을 여는 진짜 경로를 그대로 태운다. 그 위에 여러
OS 스레드로 동시에 로그인 실패를 보내 진짜 경합을 유도한다.

동시 요청 수를 ``settings.login_max_attempts``와 똑같이 맞춘 이유: 그보다 많이
보내면, 잠금이 걸린 *이후에* 시작되는 요청이 잠금 여부를 먼저 읽고 429로
분기해(카운터를 증가시키지 않고) 빠지는 경로가 섞여 들어가 "최종 카운터 값"의
기대치 자체가 흔들린다. 정확히 max_attempts개만 보내면, 그 429 분기가 전혀
끼어들 수 없어 "최종 failed_count == 보낸 실패 횟수"라는 깔끔한 불변식으로
원자성을 검증할 수 있다.
"""

from __future__ import annotations

import threading
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from evcharge.infra.models import LoginAttempt, User
from evcharge.infra.security import hash_password
from evcharge.main import create_app
from evcharge.settings import get_settings


def test_concurrent_failed_logins_increment_the_counter_atomically(test_engine):
    settings = get_settings()
    concurrency = settings.login_max_attempts
    email = f"lockout-race-{uuid.uuid4().hex}@example.com"

    # 실제 커넥션으로 직접 커밋 — db_session(SAVEPOINT) 픽스처를 쓰지 않는다.
    # 동시에 여는 요청들의 세션과 이 세션이 서로 다른 진짜 트랜잭션이어야
    # 경쟁을 재현할 수 있다.
    setup_session = DbSession(bind=test_engine)
    try:
        setup_session.add(
            User(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=hash_password("correct-horse-battery"),
                nickname="레이스",
            )
        )
        # 행을 미리 만들어 둔다: 없는 상태로 동시에 INSERT를 시도하면
        # PK(email) 충돌이라는 또 다른(그러나 이 finding과는 다른) 실패
        # 양상이 섞여, 우리가 보이고 싶은 "읽고-쓰기 lost update"가 흐려진다.
        setup_session.add(LoginAttempt(email=email, failed_count=0))
        setup_session.commit()
    finally:
        setup_session.close()

    # get_session 오버라이드가 없는 진짜 앱 — 요청마다 infra.db.get_session()이
    # 새 커넥션을 연다(conftest의 client 픽스처처럼 세션을 공유하지 않는다).
    app = create_app()

    results: list[int] = []
    results_lock = threading.Lock()

    def attempt_login() -> None:
        # 스레드마다 자기 TestClient를 써서 쿠키 저장소 등 클라이언트 쪽 상태를
        # 공유하지 않게 한다 — 서버 쪽 동시성만 측정하고 싶다.
        thread_client = TestClient(app)
        response = thread_client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrong-password"},
        )
        with results_lock:
            results.append(response.status_code)

    threads = [threading.Thread(target=attempt_login) for _ in range(concurrency)]

    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
            assert not t.is_alive(), "로그인 요청 스레드가 제한 시간 안에 끝나지 않았다"

        assert results == [401] * concurrency, (
            f"동시 로그인 실패 {concurrency}건 중 일부가 401이 아니다: {results}. "
            "max_attempts개만 보냈으니 이 시점엔 아직 아무도 잠겨 있으면 안 된다 — "
            "429가 섞였다면 카운터가 예상보다 먼저 임계값에 도달했다는 뜻이다."
        )

        verify_session = DbSession(bind=test_engine)
        try:
            attempt = verify_session.get(LoginAttempt, email)
        finally:
            verify_session.close()

        assert attempt is not None
        assert attempt.failed_count == concurrency, (
            f"동시 실패 {concurrency}건을 보냈는데 최종 failed_count="
            f"{attempt.failed_count}. 카운터 증가가 원자적이지 않으면(lost "
            "update) 이 값이 concurrency보다 작게 나온다 — 병렬 요청 중 일부의 "
            "증가분이 조용히 사라졌다는 뜻이다."
        )
        assert attempt.locked_until is not None, (
            "failed_count가 login_max_attempts에 도달했는데 잠기지 않았다."
        )
    finally:
        cleanup_session = DbSession(bind=test_engine)
        try:
            cleanup_session.query(LoginAttempt).filter_by(email=email).delete()
            cleanup_session.query(User).filter_by(email=email).delete()
            cleanup_session.commit()
        finally:
            cleanup_session.close()
