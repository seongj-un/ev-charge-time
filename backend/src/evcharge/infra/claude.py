"""Claude 호출기 (와트잇 BE-3 음성 대화).

``llm.py``(Gemini)와 같은 자리, 같은 규칙이다. 라우터와 대화 서비스는 구체 구현이
아니라 ``ClaudeClient`` 프로토콜에만 의존하고, 테스트는 가짜 클라이언트를 꽂는다.
테스트가 실제 API를 부르면 돈이 나간다.

여기가 아는 것은 "Messages API를 한 번 부르고 응답을 단순한 모양으로 바꾼다"까지다.
도구를 실행하고 루프를 도는 일, 숫자를 검증하는 일은 ``api/car_voice_service.py``가
한다.

# SDK 표면 (설치된 anthropic 2.8.0에서 확인)

- ``Anthropic(api_key=..., max_retries=...)``: ``api_key``를 명시하면 환경변수
  (``ANTHROPIC_API_KEY``, ``ANTHROPIC_AUTH_TOKEN``)와 디스크의 프로필을 보지 않는다.
  설정(.env)에 둔 키만 쓰게 하려고 늘 명시한다.
- ``client.messages.create(model, max_tokens, system, messages, tools, timeout)``:
  ``timeout``은 호출마다 줄 수 있어서, 대화 한 번 전체의 남은 시간을 넘긴다.
- 응답 ``Message.content``는 ``TextBlock(type="text", text)``와
  ``ToolUseBlock(type="tool_use", id, name, input)``의 목록이고, ``stop_reason``이
  ``"tool_use"``면 도구 결과를 기다린다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


class ClaudeError(RuntimeError):
    """Claude 호출 실패(타임아웃 포함). 문구에 API 키가 들어가지 않는다."""


@dataclass(frozen=True)
class TextPart:
    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]
    type: Literal["tool_use"] = "tool_use"


@dataclass(frozen=True)
class ClaudeReply:
    """SDK 응답에서 대화 서비스가 쓰는 부분만 옮긴 것."""

    stop_reason: str | None
    parts: list[TextPart | ToolCall]

    @property
    def text(self) -> str:
        return "".join(part.text for part in self.parts if isinstance(part, TextPart)).strip()

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [part for part in self.parts if isinstance(part, ToolCall)]


class ClaudeClient(Protocol):
    """대화 서비스가 의존하는 모양. ``messages``와 ``tools``는 Messages API 형식 그대로다."""

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        timeout_s: float,
    ) -> ClaudeReply: ...


@dataclass
class AnthropicClaudeClient:
    """``ClaudeClient``의 실제 구현."""

    api_key: str
    model: str

    _client: Any = field(default=None, init=False, repr=False)

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        timeout_s: float,
    ) -> ClaudeReply:
        client = self._ensure_client()
        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
                timeout=timeout_s,
            )
        except Exception as exc:  # noqa: BLE001 - ClaudeError로 되던진다(from None은 키 때문)
            # 타임아웃, 연결, 4xx/5xx, 응답 검증이 서로 다른 예외로 온다. 운전자에게는
            # 모두 "지금은 대답하기 어렵다"는 같은 뜻이다. 원본을 매달면 traceback에
            # 가리지 않은 문구가 찍힐 수 있어 ``from None``으로 끊는다.
            raise ClaudeError(f"Claude 호출 실패: {self._describe(exc)}") from None
        return self._to_reply(message)

    def _ensure_client(self) -> Any:
        if self._client is None:
            # SDK import를 여기서 하는 이유는 ``llm.py``와 같다: 앱 기동과 테스트 수집이
            # SDK에 묶이지 않게 한다.
            from anthropic import Anthropic

            if not self.api_key:
                raise ClaudeError("ANTHROPIC_API_KEY가 설정되지 않았다")
            # max_retries=0: 운전 중 대화라 전체 시간 예산(8초)이 정해져 있고, 보낸
            # 요청이 시간 초과로 끝났을 때 다시 보내면 같은 일을 두 번 할 수 있다.
            self._client = Anthropic(api_key=self.api_key, max_retries=0)
        return self._client

    def _to_reply(self, message: Any) -> ClaudeReply:
        parts: list[TextPart | ToolCall] = []
        for block in getattr(message, "content", None) or []:
            kind = getattr(block, "type", None)
            if kind == "text":
                parts.append(TextPart(text=str(block.text)))
            elif kind == "tool_use":
                raw = block.input if isinstance(block.input, dict) else {}
                parts.append(ToolCall(id=str(block.id), name=str(block.name), input=raw))
            # 다른 블록(thinking 등)은 쓰지 않는다.
        return ClaudeReply(stop_reason=getattr(message, "stop_reason", None), parts=parts)

    def _describe(self, exc: BaseException) -> str:
        text = str(exc)
        if self.api_key:
            text = text.replace(self.api_key, "<ANTHROPIC_API_KEY>")
        return f"{type(exc).__name__}: {text[:300]}"
