"""F-10 자연어 질의 (``POST /api/chat``).

**실제 Gemini API를 절대 부르지 않는다.** 돈이 들고 느리고 불안정하며, 무료
티어의 분당·일일 할당량을 테스트가 갉아먹는다. ``charger_api.py``를 가짜
transport로 바꿔 끼웠던 것과 같은 방식으로, 라우터가 의존하는 것은 구체
구현(``GeminiClient``)이 아니라 ``llm_client`` 의존성이라서 테스트가
``dependency_overrides``로 가짜를 꽂는다.

이 파일이 검증하는 설계 판단 두 가지:

1. **문장은 서버가 쓴다.** 모델은 "질문 → 조건 추출" 한 번만 부른다. 금액·시각은
   계산 결과를 그대로 문자열로 만들어 넣으므로 모델이 숫자를 지어낼 자리가 없다.
   ``test_the_model_is_called_exactly_once_per_question``이 그 호출 횟수를 못박는다.
2. **모델이 낸 값은 전부 의심한다.** 범위를 벗어나거나 파싱되지 않는 값은
   "모른다"로 떨어뜨려 ``missing_fields``가 되게 하고, 절대 그럴듯한 값으로
   메우지 않는다 (충전소 ``stat``/``chgerType``에서 문서에 없는 값에 여러 번
   걸렸던 것과 같은 교훈).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.api.routes.extensions import gemini_api_key, llm_client
from evcharge.domain.pricing import KST
from evcharge.infra.llm import LlmError
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.models import User, Vehicle
from evcharge.infra.security import hash_password, hash_token, new_session_token
from evcharge.settings import get_settings

# 기능 명세 시나리오 A(퇴근 후 귀가 → 다음날 출근 전)를 절대 시각으로 고정한 것.
# 도메인 탐색은 "지금"을 보지 않으므로(planner.recommend) 과거·미래 어느 쪽이든
# 결과가 같다 — 덕분에 시계를 얼리지 않고도 결정적인 기대값을 쓸 수 있다.
FULL_EXTRACTION = {
    "battery_kwh": 70,
    "soc_now": 30,
    "soc_target": 80,
    "charger_kw": 7,
    "earliest_start": "2026-10-07T18:00:00+09:00",
    "deadline": "2026-10-08T08:00:00+09:00",
    "mode": "self_low",
    "efficiency": None,
}

QUESTION = "내일 출근 전까지 80% 채우려면 언제 충전해?"


@dataclass
class FakeLlm:
    """가짜 LLM. 돌려줄 것을 테스트가 직접 정한다.

    ``payload``가 예외면 던지고, 문자열이면 그대로(=모델이 JSON이 아닌 것을 낸
    상황), 그 밖이면 JSON으로 직렬화해 돌려준다.
    """

    payload: object
    calls: list[dict] = field(default_factory=list)

    def generate_json(self, *, system_instruction: str, prompt: str, schema: type) -> str:
        self.calls.append(
            {"system_instruction": system_instruction, "prompt": prompt, "schema": schema}
        )
        if isinstance(self.payload, Exception):
            raise self.payload
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload)


@pytest.fixture(autouse=True)
def fake_llm(client) -> FakeLlm:
    """기본값은 "조건이 전부 모인" 추출 결과. 테스트가 ``.payload``로 바꾼다.

    **autouse인 이유:** 이 모듈의 어떤 테스트도 실제 SDK에 닿지 않게 하려는
    것이다. 명시적으로 요청한 테스트만 가짜를 쓰면, 새로 추가된 테스트가
    깜빡하는 순간 진짜 API를 부르게 된다. conftest의
    ``_never_call_the_real_llm``(키를 비운다)과 이중으로 막는다.
    """
    fake = FakeLlm(payload=dict(FULL_EXTRACTION))
    client.app.dependency_overrides[llm_client] = lambda: fake
    return fake


@pytest.fixture(autouse=True)
def _key_configured(client):
    """키가 설정된 상태를 기본으로 둔다.

    개발자 ``.env``에 키가 있느냐 없느냐에 따라 테스트 결과가 갈리면 안 된다
    (``test_chargers.py``의 ``_api_key_configured``와 같은 이유). 키가 없는
    경우는 그 케이스를 보는 테스트가 직접 오버라이드를 되돌린다.
    """
    client.app.dependency_overrides[gemini_api_key] = lambda: "test-key"


def _login(client, db_session, email: str | None = None) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email or f"chat-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("password123"),
        nickname="테스터",
    )
    db_session.add(user)
    # 세션 행의 FK가 users를 가리키므로 사용자를 먼저 확정한다.
    db_session.commit()
    token = new_session_token()
    db_session.add(
        SessionModel(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(KST) + timedelta(days=14),
        )
    )
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, token)
    return user


def _ask(client, message: str = QUESTION, **body):
    return client.post("/api/chat", json={"message": message, **body})


# ---------------------------------------------------------------------------
# 접근 제어 — 로그인 필요(명세), 키 없으면 501
# ---------------------------------------------------------------------------


def test_guest_is_unauthorized(client, fake_llm):
    response = _ask(client)

    assert response.status_code == 401
    assert fake_llm.calls == [], "로그인도 하지 않은 요청으로 모델을 부르면 안 된다"


def test_without_a_key_the_endpoint_is_not_implemented(client, db_session, fake_llm):
    """``charger_api_key``와 같은 규칙: 키가 비어 있으면 501.

    키 없이도 나머지 기능이 전부 돌아야 하므로 기동 시점에 막지 않는다.
    """
    _login(client, db_session)
    client.app.dependency_overrides[gemini_api_key] = lambda: ""

    response = _ask(client)

    assert response.status_code == 501
    assert isinstance(response.json()["detail"], str)
    assert fake_llm.calls == [], "키가 없으면 모델을 부르지 않는다"


def test_the_suite_never_reaches_the_real_api_by_default(client, db_session):
    """안전장치 회귀 테스트 (conftest의 ``_never_call_the_real_llm``).

    개발자 ``.env``에 진짜 키가 들어 있어도 테스트 세션에서는 비어 있어야 한다.
    이 테스트는 ``gemini_api_key`` 오버라이드를 걷어내 **진짜 설정값**을 보게
    한 뒤, 그래도 501이 나오는지 본다. 501이 아니라 200/503이 나오면 실제
    Gemini API를 부르고 있다는 뜻이다 — 돈과 무료 티어 할당량이 걸린 문제라
    조용히 지나가면 안 된다.
    """
    _login(client, db_session)
    client.app.dependency_overrides.pop(gemini_api_key)

    response = _ask(client)

    assert response.status_code == 501, (
        f"실제 설정으로 /api/chat이 {response.status_code}를 냈다 = 테스트 세션에 "
        "진짜 GEMINI_API_KEY가 살아 있다. 이 테스트 자체는 가짜 클라이언트가 "
        "autouse라 실제 호출까지 가지 않지만, 그 오버라이드를 깜빡한 테스트가 "
        "하나라도 생기면 그때는 진짜 API를 부르고 할당량을 쓴다."
    )


# ---------------------------------------------------------------------------
# 조건이 다 모인 경우 → 추천 + 문장
# ---------------------------------------------------------------------------


def test_full_conditions_produce_a_recommendation(client, db_session, fake_llm):
    _login(client, db_session)

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["missing_fields"] == []
    assert body["recommendation"] is not None
    best = body["recommendation"]["best"]
    assert best["start"].endswith("+09:00")
    assert body["recommendation"]["savings_won"] >= 0


def test_the_answer_quotes_the_computed_numbers_not_the_models(client, db_session, fake_llm):
    """금액·시각은 계산 결과를 그대로 쓴다.

    모델이 문장을 쓰면 여기에 그럴듯한 다른 숫자가 들어갈 수 있고, 그 숫자는
    사용자가 실제로 따라 하는 충전 계획이 된다. 그래서 서버가 문장을 만든다.
    """
    _login(client, db_session)

    body = _ask(client).json()
    best = body["recommendation"]["best"]
    answer = body["answer"]

    assert f"{best['cost_won']:,}원" in answer
    # 시각은 사람이 읽는 형식으로 들어가되, 계산 결과와 같은 시각이어야 한다.
    start = datetime.fromisoformat(best["start"])
    assert f"{start.month}월 {start.day}일" in answer


def test_the_model_is_called_exactly_once_per_question(client, db_session, fake_llm):
    """조건 추출 1회. 문장 작성에 모델을 또 부르지 않는다.

    무료 티어는 분당 호출 제한이 있어서, 질문 하나에 두 번 부르면 같은 할당량으로
    답할 수 있는 질문 수가 절반이 된다.
    """
    _login(client, db_session)

    _ask(client)

    assert len(fake_llm.calls) == 1


def test_the_prompt_carries_the_current_kst_time(client, db_session, fake_llm):
    """"내일 출근 전까지"는 기준 시각이 없으면 풀 수 없다."""
    _login(client, db_session)

    _ask(client)

    sent = fake_llm.calls[0]["prompt"] + fake_llm.calls[0]["system_instruction"]
    now = datetime.now(KST)
    assert now.strftime("%Y-%m-%d") in sent
    assert "+09:00" in sent


def test_the_question_reaches_the_model(client, db_session, fake_llm):
    _login(client, db_session)

    _ask(client, message="주말 낮에 충전하면 얼마나 아껴?")

    assert "주말 낮에 충전하면 얼마나 아껴?" in fake_llm.calls[0]["prompt"]


# ---------------------------------------------------------------------------
# 조건이 모자란 경우 → missing_fields, recommendation null
# ---------------------------------------------------------------------------


def test_missing_conditions_are_asked_back(client, db_session, fake_llm):
    _login(client, db_session)
    fake_llm.payload = {
        **FULL_EXTRACTION,
        "soc_target": None,
        "deadline": None,
    }

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"] is None
    assert set(body["missing_fields"]) == {"soc_target", "deadline"}
    # 되묻는 문장이 한국어로 나가야 한다 (필드 이름만 던지지 않는다).
    assert "?" in body["answer"] or "요" in body["answer"]
    assert len(body["answer"]) > 10


def test_an_empty_extraction_asks_for_everything_required(client, db_session, fake_llm):
    _login(client, db_session)
    fake_llm.payload = dict.fromkeys(FULL_EXTRACTION)

    body = _ask(client).json()

    assert body["recommendation"] is None
    assert set(body["missing_fields"]) == {
        "battery_kwh",
        "soc_now",
        "soc_target",
        "charger_kw",
        "earliest_start",
        "deadline",
    }
    # mode·efficiency는 기본값이 있으므로 "모자란 항목"이 아니다.
    assert "mode" not in body["missing_fields"]
    assert "efficiency" not in body["missing_fields"]


# ---------------------------------------------------------------------------
# 모델 출력 검증 — 지어내지 않고 "모른다"로 떨어뜨린다
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name,bad_value",
    [
        ("soc_now", 150),  # 0 <= soc_now < 100
        ("soc_now", -5),
        ("soc_target", 0),  # 0 < soc_target <= 100
        ("soc_target", 120),
        ("battery_kwh", -70),
        ("battery_kwh", 0),
        ("charger_kw", 0),
        ("earliest_start", "내일 아침"),  # ISO 8601이 아니다
        ("earliest_start", "2026-13-45T99:00"),
        ("deadline", ""),
    ],
)
def test_out_of_range_model_output_becomes_missing_not_a_guess(
    client, db_session, fake_llm, field_name, bad_value
):
    """모델이 낸 말이 안 되는 값은 버리고 "모른다"로 둔다.

    지어낸 숫자 하나가 사용자가 따라 하는 충전 계획이 된다. 그럴듯하게 고쳐
    넣는 것(예: 150 → 100)보다 되묻는 편이 항상 낫다.
    """
    _login(client, db_session)
    fake_llm.payload = {**FULL_EXTRACTION, field_name: bad_value}

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"] is None
    assert body["missing_fields"] == [field_name]


def test_an_unknown_mode_falls_back_to_the_default_instead_of_failing(
    client, db_session, fake_llm
):
    """``mode``는 Literal 3개뿐이다. 모델이 다른 문자열을 내면 버리고 기본값을 쓴다.

    ``mode``를 그대로 통과시키면 스키마 검증에서 422가 되어, 사용자는 답 대신
    오류를 본다. 모르는 값은 "말하지 않은 것"과 같게 다룬다 —
    ``RecommendRequest``의 기본값(self_low)은 ``/api/recommend``에서도 같다.
    """
    _login(client, db_session)
    fake_llm.payload = {**FULL_EXTRACTION, "mode": "초고속완속하이브리드"}

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"] is not None
    assert "mode" not in body["missing_fields"]


def test_inconsistent_conditions_are_asked_back_not_500(client, db_session, fake_llm):
    """soc_target <= soc_now 처럼 앞뒤가 맞지 않는 추출은 되묻는다."""
    _login(client, db_session)
    fake_llm.payload = {**FULL_EXTRACTION, "soc_now": 80, "soc_target": 30}

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"] is None
    assert body["missing_fields"] != []


def test_a_span_the_service_refuses_is_reported_as_a_sentence(client, db_session, fake_llm):
    """계산이 업무 오류로 끝나도(예: 시간 부족) 문장으로 답한다."""
    _login(client, db_session)
    fake_llm.payload = {
        **FULL_EXTRACTION,
        "earliest_start": "2026-10-07T18:00:00+09:00",
        "deadline": "2026-10-07T18:30:00+09:00",  # 5kWh/7kW = 7시간이 필요하다
    }

    response = _ask(client)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


# ---------------------------------------------------------------------------
# 모델 호출이 실패한 경우
# ---------------------------------------------------------------------------


def test_a_model_failure_is_a_service_error_not_a_500(client, db_session, fake_llm):
    _login(client, db_session)
    fake_llm.payload = LlmError("호출 실패")

    response = _ask(client)

    assert response.status_code == 503
    assert isinstance(response.json()["detail"], str)


def test_non_json_model_output_is_a_service_error(client, db_session, fake_llm):
    _login(client, db_session)
    fake_llm.payload = "죄송하지만 그 질문에는 답할 수 없습니다."

    response = _ask(client)

    assert response.status_code == 503
    assert isinstance(response.json()["detail"], str)


# ---------------------------------------------------------------------------
# F-12 기본 차량이 값을 채운다
# ---------------------------------------------------------------------------


def test_the_default_vehicle_fills_battery_and_charger(client, db_session, fake_llm):
    """질문에 배터리 용량·충전기 출력이 없어도 기본 차량이 있으면 계산된다."""
    user = _login(client, db_session)
    db_session.add(
        Vehicle(
            id=str(uuid.uuid4()),
            user_id=user.id,
            name="아이오닉 5",
            battery_kwh=77.4,
            charger_kw=11.0,
            mode="self_high",
            is_default=True,
        )
    )
    db_session.commit()
    fake_llm.payload = {**FULL_EXTRACTION, "battery_kwh": None, "charger_kw": None, "mode": None}

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["missing_fields"] == []
    assert body["recommendation"] is not None
    # 77.4kWh × (80-30)% = 38.7kWh
    assert body["recommendation"]["best"]["energy_kwh"] == pytest.approx(38.7)


def test_the_question_wins_over_the_default_vehicle(client, db_session, fake_llm):
    """질문에서 값을 읽어냈으면 차량 기본값으로 덮지 않는다."""
    user = _login(client, db_session)
    db_session.add(
        Vehicle(
            id=str(uuid.uuid4()),
            user_id=user.id,
            name="아이오닉 5",
            battery_kwh=77.4,
            charger_kw=11.0,
            is_default=True,
        )
    )
    db_session.commit()

    body = _ask(client).json()

    # FULL_EXTRACTION의 70kWh × 50% = 35.0kWh
    assert body["recommendation"]["best"]["energy_kwh"] == pytest.approx(35.0)


def test_a_non_default_vehicle_is_not_used(client, db_session, fake_llm):
    """기본 차량이 아니면 쓰지 않는다 — 어느 차인지 알 수 없으므로 되묻는다."""
    user = _login(client, db_session)
    db_session.add(
        Vehicle(
            id=str(uuid.uuid4()),
            user_id=user.id,
            name="세컨카",
            battery_kwh=40.0,
            charger_kw=7.0,
            is_default=False,
        )
    )
    db_session.commit()
    fake_llm.payload = {**FULL_EXTRACTION, "battery_kwh": None, "charger_kw": None}

    body = _ask(client).json()

    assert body["recommendation"] is None
    assert set(body["missing_fields"]) == {"battery_kwh", "charger_kw"}


def test_another_users_default_vehicle_is_not_used(client, db_session, fake_llm):
    other = User(
        id=str(uuid.uuid4()),
        email=f"other-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("password123"),
    )
    db_session.add(other)
    db_session.commit()
    db_session.add(
        Vehicle(
            id=str(uuid.uuid4()),
            user_id=other.id,
            name="남의 차",
            battery_kwh=100.0,
            charger_kw=50.0,
            is_default=True,
        )
    )
    db_session.commit()

    _login(client, db_session)
    fake_llm.payload = {**FULL_EXTRACTION, "battery_kwh": None, "charger_kw": None}

    body = _ask(client).json()

    assert body["recommendation"] is None
    assert set(body["missing_fields"]) == {"battery_kwh", "charger_kw"}


# ---------------------------------------------------------------------------
# 사용자별 호출 제한 → 429
# ---------------------------------------------------------------------------


@pytest.fixture
def small_limit(monkeypatch) -> int:
    """제한을 3으로 낮춘다. ``get_settings()``는 매번 새로 읽으므로 환경변수면 된다."""
    monkeypatch.setenv("CHAT_RATE_LIMIT_COUNT", "3")
    return 3


def test_the_limit_is_per_user_and_returns_429(client, db_session, fake_llm, small_limit):
    _login(client, db_session)

    statuses = [_ask(client).status_code for _ in range(small_limit + 2)]

    assert statuses == [200] * small_limit + [429, 429], statuses
    assert len(fake_llm.calls) == small_limit, "제한을 넘긴 요청으로 모델을 부르면 안 된다"


def test_another_user_has_their_own_budget(client, db_session, fake_llm, small_limit):
    _login(client, db_session)
    for _ in range(small_limit):
        assert _ask(client).status_code == 200
    assert _ask(client).status_code == 429

    # 같은 TestClient의 쿠키만 갈아끼워 다른 사용자로 로그인한다.
    _login(client, db_session)

    assert _ask(client).status_code == 200


def test_a_failed_model_call_still_costs_quota(client, db_session, fake_llm, small_limit):
    """실패한 호출도 무료 티어 할당량을 깎는다 — 세지 않으면 제한을 무료로 우회할 수 있다."""
    _login(client, db_session)
    fake_llm.payload = LlmError("호출 실패")

    for _ in range(small_limit):
        assert _ask(client).status_code == 503

    assert _ask(client).status_code == 429


# ── 429에 언제 다시 물어볼 수 있는지 담는다 ─────────────────────────────


def test_429_carries_retry_after_seconds(client, db_session, fake_llm, small_limit):
    """제한에 걸리면 Retry-After 헤더로 남은 시간을 알려준다.

    서버는 창이 언제 리셋되는지 알고 있다. 그걸 안 알려주면 화면은 한도만
    말할 수 있고, 사용자는 언제 다시 물어볼 수 있는지 모른 채 계속 누른다.
    Retry-After는 429에 대한 표준 헤더라 프론트가 따로 약속할 것도 없다.
    """
    _login(client, db_session)

    for _ in range(small_limit):
        assert _ask(client).status_code == 200

    blocked = _ask(client)
    assert blocked.status_code == 429

    retry_after = blocked.headers.get("retry-after")
    assert retry_after is not None, "429에 Retry-After가 없다"
    seconds = int(retry_after)

    window_seconds = get_settings().chat_rate_limit_window_minutes * 60
    # 창이 막 시작했을 수도, 거의 끝나갈 수도 있으므로 범위로 본다.
    # 0이면 "지금 다시 해보라"는 뜻이 되어 무한 재시도를 부른다.
    assert 0 < seconds <= window_seconds, seconds


def test_429_body_says_when_not_just_that_it_is_limited(
    client, db_session, fake_llm, small_limit
):
    """본문에도 남은 시간을 담는다 — 헤더를 못 읽는 화면도 있다."""
    _login(client, db_session)

    for _ in range(small_limit):
        _ask(client)

    detail = _ask(client).json()["detail"]
    assert "분" in detail, detail


def test_a_model_failure_log_does_not_carry_the_original_exception(
    client, db_session, fake_llm, caplog
):
    """503 경로의 로그는 ``LlmError``의 (이미 가린) 문구만 남긴다.

    예전에는 ``exc_info=True``라서 ``LlmError``에 매달린 원본 예외까지 traceback으로
    찍혔다. 원본 문구에 키가 들어 있으면 바깥 문구를 아무리 가려도 로그로 샜다.
    """
    secret = "AIzaSy-route-level-fake-key-000000"
    _login(client, db_session)
    try:
        try:
            raise RuntimeError(f"401 key={secret}")
        except RuntimeError as original:
            raise LlmError("모델 호출 실패: <GEMINI_API_KEY>") from original
    except LlmError as chained:
        fake_llm.payload = chained

    with caplog.at_level("WARNING"):
        response = _ask(client)

    assert response.status_code == 503
    assert "자연어 질의 실패" in caplog.text
    assert secret not in caplog.text


# ---------------------------------------------------------------------------
# 공용 급속 단가 — 추출·전달하고, 없으면 되묻는다
# ---------------------------------------------------------------------------
#
# 공용 급속은 충전사업자마다 단가가 달라 단가 없이는 계산할 수 없다. 예전에는
# 추출 스키마에 단가 자리가 없어서 사용자가 "350원"이라고 말해도 버려졌고,
# 계산 단계에서 422(단가를 알려 달라는 문장)가 났다.


def test_a_public_fast_price_in_the_question_reaches_the_calculation(
    client, db_session, fake_llm
):
    _login(client, db_session)
    fake_llm.payload = {**FULL_EXTRACTION, "mode": "public_fast", "public_base_price": 350}

    response = _ask(client, "공용 급속(350원/kWh)으로 내일 출근 전까지 80% 채우려면?")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["missing_fields"] == []
    # 10월 7일(수) 18시~ — 할인 없는 평일이라 70kWh × 50% × 350원
    assert body["recommendation"]["best"]["cost_won"] == 35 * 350


def test_public_fast_without_a_price_is_asked_back(client, db_session, fake_llm):
    _login(client, db_session)
    fake_llm.payload = {**FULL_EXTRACTION, "mode": "public_fast", "public_base_price": None}

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"] is None
    assert body["missing_fields"] == ["public_base_price"]
    assert "단가" in body["answer"]


def test_a_missing_price_is_asked_together_with_other_missing_fields(
    client, db_session, fake_llm
):
    """한 번에 모아서 묻는다 — 답하자마자 또 다른 걸 되물으면 대화가 늘어진다."""
    _login(client, db_session)
    fake_llm.payload = {
        **FULL_EXTRACTION,
        "mode": "public_fast",
        "public_base_price": None,
        "soc_target": None,
    }

    body = _ask(client).json()

    assert body["missing_fields"] == ["soc_target", "public_base_price"]


def test_a_public_fast_default_vehicle_asks_for_the_price(client, db_session, fake_llm):
    """방식은 기본 차량에서 왔고 질문에는 단가가 없다 → 단가를 되묻는다."""
    user = _login(client, db_session)
    db_session.add(
        Vehicle(
            id=str(uuid.uuid4()),
            user_id=user.id,
            name="출장용",
            battery_kwh=70.0,
            charger_kw=50.0,
            mode="public_fast",
            is_default=True,
        )
    )
    db_session.commit()
    fake_llm.payload = {**FULL_EXTRACTION, "mode": None, "public_base_price": None}

    response = _ask(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["recommendation"] is None
    assert body["missing_fields"] == ["public_base_price"]


def test_an_absurd_public_fast_price_is_dropped_and_asked_back(client, db_session, fake_llm):
    _login(client, db_session)
    fake_llm.payload = {**FULL_EXTRACTION, "mode": "public_fast", "public_base_price": 1e300}

    body = _ask(client).json()

    assert body["missing_fields"] == ["public_base_price"]
