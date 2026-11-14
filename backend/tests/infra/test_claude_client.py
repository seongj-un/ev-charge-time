"""``AnthropicClaudeClient``: SDK 응답 변환, 예외 감싸기, 키 가리기. 실제 API는 부르지 않는다."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from evcharge.infra.claude import AnthropicClaudeClient, ClaudeError, TextPart, ToolCall

KEY = "sk-ant-test-0123456789abcdef"


class _FakeMessages:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result, self.error, self.kwargs = result, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.result


def _client(messages: _FakeMessages) -> AnthropicClaudeClient:
    client = AnthropicClaudeClient(api_key=KEY, model="claude-haiku-5-5")
    client._client = SimpleNamespace(messages=messages)
    return client


def _call(client: AnthropicClaudeClient):
    return client.create(system="s", messages=[], tools=[], max_tokens=300, timeout_s=5.5)


def test_reply_keeps_text_and_tool_calls_and_passes_timeout():
    message = SimpleNamespace(
        stop_reason="tool_use",
        content=[
            SimpleNamespace(type="text", text="잠시만요. "),
            SimpleNamespace(type="tool_use", id="t1", name="plan_charge", input={"a": 1}),
            SimpleNamespace(type="thinking", thinking="..."),
        ],
    )
    messages = _FakeMessages(result=message)

    reply = _call(_client(messages))

    assert reply.stop_reason == "tool_use"
    assert reply.parts == [
        TextPart(text="잠시만요. "),
        ToolCall(id="t1", name="plan_charge", input={"a": 1}),
    ]
    assert reply.text == "잠시만요."
    assert messages.kwargs["timeout"] == 5.5
    assert messages.kwargs["model"] == "claude-haiku-5-5"
    assert messages.kwargs["max_tokens"] == 300


def test_sdk_errors_become_claude_error_without_the_key():
    messages = _FakeMessages(error=RuntimeError(f"bad request with x-api-key {KEY}"))

    with pytest.raises(ClaudeError) as caught:
        _call(_client(messages))

    assert KEY not in str(caught.value)
    assert "<ANTHROPIC_API_KEY>" in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_real_sdk_client_is_built_with_the_explicit_key_and_no_retries():
    client = AnthropicClaudeClient(api_key=KEY, model="m")

    sdk = client._ensure_client()

    assert sdk.api_key == KEY
    assert sdk.max_retries == 0


def test_missing_key_is_claude_error():
    with pytest.raises(ClaudeError):
        AnthropicClaudeClient(api_key="", model="m")._ensure_client()
