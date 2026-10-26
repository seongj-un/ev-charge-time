"""Gemini 호출기 (F-10).

``charger_api.py``와 같은 자리, 같은 모양이다 — 외부 API를 부르는 코드는
infra에 두고, 라우터는 구체 구현이 아니라 ``LlmClient`` 프로토콜에만 의존해서
테스트가 가짜를 꽂을 수 있게 한다. 테스트가 실제 API를 부르면 돈이 나가고,
느리고, 무료 티어의 분당·일일 할당량을 갉아먹는다.

여기가 아는 것은 "JSON 하나를 받아온다"까지다. 프롬프트를 만들고 그 JSON을
검증하는 일은 ``api/chat_service.py``가 한다.

# 어느 표면을 쓰는가 (설치된 SDK를 직접 확인한 결과)

google-genai **2.24.0** 에는 두 표면이 **모두** 있다. 실제로 확인한 것:

* ``client.interactions.create`` — 존재한다. 다만 런타임 시그니처는 공개
  래퍼·생성된 기반 클래스 양쪽 모두 ``(*, request=None, ..., **body: Any)`` 라
  ``model``/``input``/``response_format`` 이 전부 타입 없는 통과 인자다.
  타입이 붙은 요청 모델(``CreateModelInteraction``)은 ``google.genai._gaos``
  **비공개 패키지**(밑줄) 안에 있다.
* ``client.models.generate_content`` — 존재하고, 2.24.0에서 폐기 표시가 없다
  (폐기된 것은 generate_images·edit_image·generate_videos뿐이다). 시그니처가
  ``(model, contents, config: GenerateContentConfig)``로 전부 타입이 붙어 있고,
  설정·응답 타입이 공개 경로(``google.genai.types``)에 있다.

**``models.generate_content``를 골랐다.** 근거:

1. 공개 import 경로만 쓴다. Interactions의 타입을 쓰려면 ``_gaos``라는 비공개
   패키지를 import해야 하고, 그건 마이너 버전에서 조용히 재배치될 수 있다.
2. ``response_schema``에 pydantic 모델을 그대로 넘기면 SDK가 nullable까지 살려
   OpenAPI 스키마로 변환한다(``_transformers.t_schema``로 확인했다). F-10의
   핵심 요구가 "모르는 값은 null"이라, 그 null 허용이 모델에게 가는 스키마에
   박히는 것이 중요하다 — 특히 빈칸을 그럴듯하게 메우려는 경향이 있는 경량
   모델(Flash-Lite)에서는 더 그렇다.
3. ``v1beta/models/{model}:generateContent``는 오래 굴러온 경로다.
   ``v1beta/interactions``는 새 표면이고, 키가 없어 어느 쪽도 실제 호출로
   검증할 수 없는 상황에서는 주행거리가 긴 쪽이 안전하다.

바꿔야 할 일이 생기면 이 파일의 ``generate_json`` 한 메서드만 고치면 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel


class LlmError(RuntimeError):
    """LLM 호출 실패. 문구에 API 키가 절대 들어가지 않는다."""


class LlmClient(Protocol):
    """라우터가 의존하는 것은 이 모양뿐이다.

    반환값이 파싱된 객체가 아니라 **원본 JSON 문자열**인 이유: 호출자가 같은
    스키마로 한 번 더 검증하게 하려는 것이다. SDK의 ``response.parsed``를 믿고
    그대로 쓰면 "모델이 낸 값"과 "우리가 허용하는 값"의 구분이 사라진다 —
    모델 출력은 외부 입력이고, 이 프로젝트는 문서에 없는 외부 값(충전소
    ``stat``·``chgerType``)에 이미 여러 번 걸렸다.
    """

    def generate_json(
        self, *, system_instruction: str, prompt: str, schema: type[BaseModel]
    ) -> str: ...


@dataclass
class GeminiClient:
    """``LlmClient``의 실제 구현. Google Gemini (무료 티어)."""

    api_key: str
    model: str
    # 사용자가 화면 앞에서 기다리는 요청이다. 오래 매달리느니 빨리 실패하고
    # 503으로 안내하는 편이 낫다.
    timeout_s: float = 20.0
    # 조건 추출은 창작이 아니라 받아쓰기다. 같은 질문에 같은 답이 나와야 한다.
    temperature: float = 0.0
    max_output_tokens: int = 1024

    _client: Any = field(default=None, init=False, repr=False)

    def generate_json(
        self, *, system_instruction: str, prompt: str, schema: type[BaseModel]
    ) -> str:
        # SDK import를 메서드 안에서 하는 이유: 앱 기동과 테스트 수집이
        # google-genai에 묶이지 않게 하려는 것이다. 키가 없으면 라우터가 이
        # 메서드에 닿기 전에 501로 끊고, 테스트는 가짜 클라이언트만 쓴다.
        from google.genai import types

        client = self._ensure_client()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    # 이 둘이 한 쌍이다. mime_type만 주면 스키마 없이 "아무
                    # JSON"이 오고, schema만 주면 무시된다.
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=self.temperature,
                    max_output_tokens=self.max_output_tokens,
                    http_options=types.HttpOptions(timeout=int(self.timeout_s * 1000)),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - LlmError로 되던진다(from None은 키 때문)
            # 좁게 잡을 수가 없다. SDK는 APIError(4xx/5xx) 말고도 전송 계층
            # (httpx), 인증(google-auth), 스키마 변환에서 서로 다른 예외를
            # 낸다. 어느 쪽이든 사용자에게는 "지금은 답할 수 없다"는 같은 뜻이고,
            # 잡지 않으면 500으로 새면서 내부 사정이 그대로 노출된다.
            # ``from None``: 원본 예외를 매달면 traceback에 가리지 않은 원본 문구가
            # 그대로 찍힌다. 원인 파악에 필요한 종류와 (가린) 문구는 메시지에 싣는다.
            raise LlmError(f"모델 호출 실패: {self._describe(exc)}") from None

        text = self._output_text(response)
        if not text or not text.strip():
            # 안전 필터에 걸리거나 max_output_tokens에서 잘리면 본문이 빈다.
            raise LlmError("모델이 빈 응답을 돌려줬다")
        return text

    # ------------------------------------------------------------------
    # 내부
    # ------------------------------------------------------------------

    def _ensure_client(self) -> Any:
        """``genai.Client``를 첫 호출에서만 만든다.

        의존성(``routes/extensions.py``의 ``llm_client``)은 요청마다 해석되는데,
        거기서 바로 SDK 클라이언트를 만들면 키가 없을 때 501을 내기도 전에 터진다.
        """
        if self._client is None:
            from google import genai

            if not self.api_key:
                raise LlmError("GEMINI_API_KEY가 설정되지 않았다")
            # 환경변수 자동 해석에 기대지 않고 설정값을 명시적으로 넘긴다 —
            # .env로만 넣은 키(환경변수에는 없다)도 그대로 동작해야 한다.
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _output_text(self, response: Any) -> str:
        """``response.text``. 접근 자체가 터질 수 있어 감싼다.

        후보가 0개이거나(안전 필터) 파트가 텍스트가 아니면 SDK가 예외를 내거나
        경고와 함께 None을 준다.
        """
        try:
            return response.text or ""
        except Exception as exc:  # noqa: BLE001 - LlmError로 되던진다(from None은 키 때문)
            # 위와 같은 이유로 넓게 잡는다. (BLE001은 `from exc`로 되던지면 잡지
            # 않지만, 키가 든 원본을 매달지 않으려고 `from None`을 써서 noqa가 필요하다.)
            raise LlmError(f"모델 응답을 읽지 못했다: {self._describe(exc)}") from None

    def _describe(self, exc: BaseException) -> str:
        return f"{type(exc).__name__}: {self._mask(str(exc))}"

    def _mask(self, text: str) -> str:
        """예외 문구에 되비쳐 나온 API 키를 지운다 (``charger_api.py``와 같은 이유).

        SDK는 키를 헤더로 싣지만, 재시도 로그나 예외 문구에 요청 정보가 통째로
        실리는 경로가 있을 수 있다. 로그·에러 트래킹으로 키가 새면 끝이다.
        """
        if not self.api_key:
            return text
        return text.replace(self.api_key, "<GEMINI_API_KEY>")
