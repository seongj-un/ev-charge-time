"""``infra/llm.py`` — Gemini 호출기의 실패 경로.

**네트워크를 타지 않는다.** ``GeminiClient``가 SDK 클라이언트를 첫 호출에서야
만들고(``_ensure_client``) 그 자리를 속성 하나로 열어 두기 때문에, 가짜 객체를
꽂으면 실제 호출 없이 실패 경로를 전부 돌아볼 수 있다 — ``charger_api.py``를
``httpx.MockTransport``로 검증했던 것과 같은 방식이다.

정상 경로(실제 모델이 스키마대로 JSON을 주는 것)는 여기서 검증하지 않는다.
키가 없으면 확인할 수 없고, 있어도 테스트가 실제 API를 부르면 안 된다. 그쪽은
``tests/api/test_chat.py``가 가짜 클라이언트로 계약 단위로 본다.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from evcharge.infra.llm import GeminiClient, LlmError

# 로그·예외 문구로 절대 새면 안 되는 값. 진짜 키 형식을 흉내냈다.
SECRET_KEY = "AIzaSy-fake-key-for-tests-only-0000000000"


class _Schema(BaseModel):
    value: str | None = None


def _client(api_key: str = SECRET_KEY, sdk: object | None = None) -> GeminiClient:
    client = GeminiClient(api_key=api_key, model="gemini-3.1-flash-lite")
    if sdk is not None:
        # _ensure_client()가 이미 채워진 것으로 보고 SDK를 만들지 않는다.
        client._client = sdk
    return client


def _call(client: GeminiClient) -> str:
    return client.generate_json(
        system_instruction="시스템", prompt="질문", schema=_Schema
    )


class _Models:
    def __init__(self, behaviour):
        self._behaviour = behaviour

    def generate_content(self, **kwargs):
        return self._behaviour(kwargs)


class _Sdk:
    def __init__(self, behaviour):
        self.models = _Models(behaviour)


class _Response:
    def __init__(self, text):
        self._text = text

    @property
    def text(self):
        if isinstance(self._text, Exception):
            raise self._text
        return self._text


def test_an_empty_key_fails_before_any_call():
    """키가 없으면 SDK를 만들지도 않는다. 라우터가 501로 먼저 끊지만, 이건 그 뒤의 안전망이다."""
    with pytest.raises(LlmError):
        _call(_client(api_key=""))


def test_sdk_errors_become_llm_errors():
    """SDK가 무엇을 던지든 ``LlmError`` 하나로 좁힌다 — 라우터는 503만 알면 된다."""
    sdk = _Sdk(lambda _: (_ for _ in ()).throw(RuntimeError("503 backend unavailable")))

    with pytest.raises(LlmError) as exc_info:
        _call(_client(sdk=sdk))

    assert "모델 호출 실패" in str(exc_info.value)


def test_the_api_key_never_leaks_into_the_error_message():
    """예외 문구에 되비쳐 나온 키를 가린다 (``charger_api.py``의 ``_mask``와 같은 이유).

    로그나 에러 트래킹으로 키가 한 번 새면 끝이다. 인증 실패 응답이 보낸 키를
    그대로 실어 주는 경우가 실제로 있다.
    """
    sdk = _Sdk(
        lambda _: (_ for _ in ()).throw(
            RuntimeError(f"401 Unauthorized: key={SECRET_KEY} rejected")
        )
    )

    with pytest.raises(LlmError) as exc_info:
        _call(_client(sdk=sdk))

    message = str(exc_info.value)
    assert SECRET_KEY not in message, "API 키가 예외 문구로 샜다"
    assert "<GEMINI_API_KEY>" in message


@pytest.mark.parametrize("text", ["", "   ", None])
def test_an_empty_response_is_an_error(text):
    """안전 필터에 걸리거나 max_output_tokens에서 잘리면 본문이 빈다.

    빈 문자열을 그대로 돌려주면 호출자가 JSON 파싱에서 알아보기 어려운 오류로
    만나게 된다. 여기서 끊는 편이 낫다.
    """
    sdk = _Sdk(lambda _: _Response(text))

    with pytest.raises(LlmError) as exc_info:
        _call(_client(sdk=sdk))

    assert "빈 응답" in str(exc_info.value)


def test_reading_the_response_text_can_fail_and_is_wrapped():
    """후보가 0개면 ``response.text`` 접근 자체가 터진다."""
    sdk = _Sdk(lambda _: _Response(ValueError("no candidates")))

    with pytest.raises(LlmError) as exc_info:
        _call(_client(sdk=sdk))

    assert "모델 응답을 읽지 못했다" in str(exc_info.value)


def test_a_good_response_comes_back_as_raw_json_text():
    """반환값은 파싱된 객체가 아니라 원본 JSON 문자열이다.

    호출자가 같은 스키마로 한 번 더 검증하게 하려는 의도다 — 모델 출력은
    외부 입력이고, SDK의 파싱 결과를 그대로 믿지 않는다.
    """
    sdk = _Sdk(lambda _: _Response('{"value": "확인"}'))

    assert _call(_client(sdk=sdk)) == '{"value": "확인"}'


def test_the_request_carries_the_model_schema_and_json_mime_type():
    """스키마와 mime_type은 한 쌍이다. 하나만 보내면 구조화 출력이 동작하지 않는다."""
    seen: dict = {}

    def capture(kwargs):
        seen.update(kwargs)
        return _Response('{"value": "확인"}')

    _call(_client(sdk=_Sdk(capture)))

    assert seen["model"] == "gemini-3.1-flash-lite"
    assert seen["contents"] == "질문"
    config = seen["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is _Schema
    assert config.system_instruction == "시스템"
    # 추출은 창작이 아니다 — 같은 질문에 같은 답이 나와야 한다.
    assert config.temperature == 0.0
    # 사용자가 화면 앞에서 기다린다. 무한정 매달리지 않는다(밀리초 단위).
    assert config.http_options.timeout == 20_000
