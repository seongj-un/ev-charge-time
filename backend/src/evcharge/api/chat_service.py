"""F-10 자연어 질의: 질문 → 조건 추출 → 되묻기 → 추천 → 한국어 문장.

# 모델에게 맡긴 것과 맡기지 않은 것

**모델은 "질문 → 조건 추출" 한 번만 부른다. 문장은 서버가 쓴다.**

지시서가 판단에 맡긴 부분이라 근거를 남긴다:

1. 금액과 시각을 모델이 쓰게 하면 언젠가 다른 숫자를 쓴다. 그리고 그 숫자는
   사용자가 실제로 따라 하는 충전 계획이 된다 — "3,120원" 대신 "약 3,000원"만
   돼도 F-04(절감액)가 거짓말이 되고, 시작 시각이 한 시간 밀리면 경부하
   시간대를 벗어난다. 계산 결과를 문자열로 만드는 것은 결정적이고, LLM 없이
   테스트할 수 있다.
2. 질문 하나에 모델 호출이 1회로 끝난다. 무료 티어는 분당 호출 한도가 프로젝트
   전체에 걸려서, 2회로 늘리면 같은 예산으로 답할 수 있는 질문이 절반이 된다.
3. 쓰기로 한 모델이 Flash-Lite(가장 저렴·가벼운 등급)다. 추론을 덜 요구할수록
   결과가 안정적이고, 조건 추출은 이 등급이 감당하는 종류의 일이다.

잃는 것은 답변 문장의 다양성이다. 심사 시연에서 같은 질문에 같은 문장이 나오는
것은 손해가 아니라 이득이라 판단했다.

# 모델 출력은 외부 입력이다

이 프로젝트는 문서에 없는 외부 값(충전소 ``stat``·``chgerType``)에 이미 여러 번
걸렸다. 모델 출력에는 그 이상의 의심이 필요하다 — 경량 모델일수록 빈칸을
그럴듯한 값으로 메우려 한다. 그래서 모든 필드를 하나씩 범위까지 확인하고,
통과하지 못한 값은 **고치지 않고 버린다**(= ``missing_fields``로 되묻는다).
150%를 100%로 "고쳐" 주는 것이 사용자에게 가장 나쁜 답이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import get_args

from pydantic import BaseModel, Field, ValidationError

from ..domain.pricing import KST
from ..infra.llm import LlmClient, LlmError
from .schemas import (
    MAX_BATTERY_KWH,
    MAX_CHARGER_KW,
    MAX_PRICE_PER_KWH,
    ChatResponse,
    Mode,
    RecommendRequest,
    RecommendResponse,
)

# 추천 계산에 반드시 있어야 하는 항목. mode·efficiency는
# ``RecommendRequest``에 기본값이 있으므로 "모자란 항목"이 아니다.
REQUIRED_FIELDS: tuple[str, ...] = (
    "battery_kwh",
    "soc_now",
    "soc_target",
    "charger_kw",
    "earliest_start",
    "deadline",
)

# 되물을 때 쓰는 한국어 이름. 필드 이름을 그대로 문장에 넣으면 사용자가 읽을 수 없다.
FIELD_LABELS: dict[str, str] = {
    "battery_kwh": "배터리 용량(kWh)",
    "soc_now": "현재 배터리 잔량(%)",
    "soc_target": "목표 배터리 잔량(%)",
    "charger_kw": "충전기 출력(kW)",
    "earliest_start": "충전을 시작할 수 있는 가장 이른 시각",
    "deadline": "충전을 마쳐야 하는 시각",
    "public_base_price": "공용 급속 충전 단가(원/kWh)",
}

# 공용 급속은 충전사업자마다 단가가 달라 하나의 공식 값이 없다. 방식이
# public_fast면 이 항목도 있어야 계산할 수 있다.
PUBLIC_FAST_PRICE = "public_base_price"

MODE_LABELS: dict[str, str] = {
    "self_low": "자가 충전(저압)",
    "self_high": "자가 충전(고압)",
    "public_fast": "공용 급속 충전",
}


class ExtractedConditions(BaseModel):
    """모델에게 넘기는 출력 스키마이자, 모델이 돌려준 JSON을 받는 그릇.

    타입이 전부 느슨한(Optional, 시각은 ``str``) 이유는 두 가지다:

    * **null이 정상 답이어야 한다.** 질문에 없는 값을 모델이 지어내지 않게
      하려면 "모른다"를 표현할 자리가 스키마에 있어야 한다. SDK가 이 모델을
      OpenAPI 스키마로 변환할 때 ``nullable: true``가 그대로 실린다.
    * **여기서 터지면 안 된다.** 모델이 낸 값이 범위를 벗어나거나 형식이
      틀렸을 때 pydantic이 예외를 내면 요청 전체가 실패한다. 그건 "그 항목만
      모른다"로 다뤄야 할 상황이다. 그래서 형식·범위 검사는 이 모델이 아니라
      아래 ``_normalize``가 필드 단위로 한다.
    """

    battery_kwh: float | None = Field(
        default=None, description="차량 배터리 총 용량(kWh). 질문에 없으면 null"
    )
    soc_now: float | None = Field(
        default=None, description="현재 배터리 잔량(%). 0 이상 100 미만. 없으면 null"
    )
    soc_target: float | None = Field(
        default=None, description="목표 배터리 잔량(%). 0 초과 100 이하. 없으면 null"
    )
    charger_kw: float | None = Field(
        default=None, description="충전기 출력(kW). 질문에 없으면 null"
    )
    earliest_start: str | None = Field(
        default=None,
        description=(
            "충전을 시작할 수 있는 가장 이른 시각. "
            "ISO 8601 + 오프셋 (예: 2026-10-07T18:00:00+09:00). 없으면 null"
        ),
    )
    deadline: str | None = Field(
        default=None,
        description=(
            "충전을 마쳐야 하는 시각. ISO 8601 + 오프셋 "
            "(예: 2026-10-08T08:00:00+09:00). 없으면 null"
        ),
    )
    mode: str | None = Field(
        default=None,
        description=(
            "충전 방식. self_low(자가 저압) / self_high(자가 고압) / "
            "public_fast(공용 급속) 중 하나. 질문에서 알 수 없으면 null"
        ),
    )
    efficiency: float | None = Field(
        default=None, description="충전 효율. 0 초과 1 이하. 질문에 없으면 null"
    )
    public_base_price: float | None = Field(
        default=None,
        description="공용 급속 충전 단가(원/kWh). 질문에 단가를 말하지 않았으면 null",
    )


@dataclass
class NormalizedConditions:
    """``ExtractedConditions``를 우리 계약에 맞게 걸러낸 결과. 통과 못 한 값은 None."""

    battery_kwh: float | None = None
    soc_now: float | None = None
    soc_target: float | None = None
    charger_kw: float | None = None
    earliest_start: datetime | None = None
    deadline: datetime | None = None
    mode: Mode | None = None
    efficiency: float | None = None
    public_base_price: float | None = None


SYSTEM_INSTRUCTION = """\
너는 한국 전기차 충전 요금 계산 서비스의 조건 추출기다.
사용자의 한국어 질문에서 충전 계획 계산에 필요한 값만 뽑아 JSON으로 답한다.

규칙:
1. 질문에 없고 합리적으로 추론할 수도 없는 값은 반드시 null로 둔다.
   그럴듯한 값을 지어내지 마라. 빈칸은 서비스가 사용자에게 다시 물어본다.
   틀린 값 하나가 사용자가 실제로 따라 하는 충전 계획이 된다.
2. 절대 계산하거나 추천하지 마라. 요금·절감액·최적 시각은 서비스가 계산한다.
3. 시각은 아래에 주어진 현재 시각(KST)을 기준으로 풀어서,
   ISO 8601 +09:00 오프셋 형식으로 쓴다.
   - "지금부터"·시작 시각을 말하지 않았으면 earliest_start는 현재 시각으로 둔다.
   - "내일 출근 전까지"처럼 마감만 말하면 deadline만 채우고 나머지는 null이다.
   - 출근 시각을 따로 말하지 않았다면 다음 날 오전 8시로 본다.
4. soc_now/soc_target은 퍼센트 숫자다("80%" → 80). "완충"은 100이다.
5. mode는 self_low·self_high·public_fast 중 하나만 쓴다.
   집(자택·아파트)에서 충전하면 self_low, 공용 급속·충전소면 public_fast다.
   확신이 없으면 null로 둔다.
6. 차종·배터리 용량·충전기 출력을 질문에서 말하지 않았다면 null이다.
   차종 이름만으로 용량을 추측하지 마라.
7. 공용 급속 충전 단가를 말했으면 public_base_price에 원/kWh 숫자로 쓴다
   ("kWh당 350원" → 350). 말하지 않았으면 null이다. 단가를 추측하지 마라.\
"""


def build_prompt(message: str, now: datetime, history: list[dict] | None = None) -> str:
    """모델에게 보낼 사용자 프롬프트.

    현재 시각을 **프롬프트 본문에** 넣는다. "내일 출근 전까지"는 기준 시각이
    없으면 풀 수 없고, 모델은 오늘이 며칠인지 모른다. 요일까지 적는 이유는
    "주말"·"평일" 같은 표현과, 요금이 갈리는 토·일 구분 때문이다.
    """
    weekday = "월화수목금토일"[now.weekday()]
    lines = [
        f"현재 시각(KST): {now.isoformat(timespec='seconds')} ({weekday}요일)",
    ]
    if history:
        lines.append("")
        lines.append("이전 대화:")
        lines.extend(_history_lines(history))
    lines.append("")
    lines.append("질문:")
    lines.append(message)
    return "\n".join(lines)


def extract_conditions(
    client: LlmClient, message: str, now: datetime, history: list[dict] | None = None
) -> NormalizedConditions:
    """모델을 한 번 불러 조건을 뽑고, 값마다 우리 계약에 맞는지 확인한다.

    ``LlmError``는 그대로 올려보낸다 — 라우터가 503으로 옮긴다.
    """
    raw = client.generate_json(
        system_instruction=SYSTEM_INSTRUCTION,
        prompt=build_prompt(message, now, history),
        schema=ExtractedConditions,
    )
    try:
        extracted = ExtractedConditions.model_validate_json(raw)
    except ValidationError as exc:
        # 스키마를 줬는데도 다른 것이 올 수 있다(안전 필터 문구, 설명 문장,
        # 코드 펜스). 그건 우리가 고칠 수 있는 게 아니라 호출 실패와 같다.
        raise LlmError("모델이 예상한 형식의 JSON을 돌려주지 않았다") from exc

    return _normalize(extracted, now)


def answer(
    conditions: NormalizedConditions,
    *,
    has_default_vehicle: bool,
    build_recommendation,
    now: datetime,
) -> ChatResponse:
    """조건이 다 모였으면 계산해서 문장으로, 모자라면 되묻는 문장으로 답한다.

    ``build_recommendation``은 "완성된 ``RecommendRequest`` → ``RecommendResponse``"
    콜백이다. 차량 기본값 병합(F-12)과 추천 계산이 둘 다 DB 세션·앱 설정을
    필요로 해서 라우터가 들고 있고, 이 모듈은 순수하게 문장만 책임진다.
    """
    request = _to_request(conditions)
    if request is None:
        missing = _missing_fields(conditions, has_default_vehicle=has_default_vehicle)
        return ChatResponse(answer=_ask_back(missing), recommendation=None, missing_fields=missing)

    result, request = build_recommendation(request)
    if result is None:
        # 차량 기본값까지 병합했는데도 배터리 용량·충전기 출력이 비었거나,
        # (기본 차량에서 온) 공용 급속 방식인데 단가가 없다.
        missing = [
            name
            for name in ("battery_kwh", "charger_kw")
            if getattr(request, name, None) is None
        ]
        if request.mode == "public_fast" and request.public_base_price is None:
            missing.append(PUBLIC_FAST_PRICE)
        return ChatResponse(answer=_ask_back(missing), recommendation=None, missing_fields=missing)

    return ChatResponse(
        answer=compose_answer(result, request, now),
        recommendation=result,
        missing_fields=[],
    )


def compose_answer(
    result: RecommendResponse, request: RecommendRequest, now: datetime
) -> str:
    """계산 결과를 한국어 문장으로. **숫자는 전부 ``result``에서 그대로 온다.**"""
    best = result.best
    start = _moment(best.start, now)
    end = _moment(best.end, now)
    mode_label = MODE_LABELS.get(request.mode, request.mode)

    sentences = [
        f"{start}부터 {end}까지 충전하시는 것이 가장 저렴합니다.",
        f"{mode_label} 기준으로 {best.energy_kwh:,.1f}kWh를 채우는 데 "
        f"약 {best.cost_won:,}원이 듭니다.",
    ]

    if result.savings_won > 0:
        sentences.append(
            f"지금 바로 충전하면 {result.baseline_now.cost_won:,}원이므로, "
            f"{result.savings_won:,}원을 아낄 수 있습니다."
        )
    else:
        sentences.append("지금 바로 충전하는 것과 비용 차이는 없습니다.")

    if best.discounted_kwh > 0:
        sentences.append(
            f"이 중 {best.discounted_kwh:,.1f}kWh가 경부하 시간대 요금으로 계산됐습니다."
        )

    return " ".join(sentences)


# ---------------------------------------------------------------------------
# 내부 — 모델 출력 검증
# ---------------------------------------------------------------------------


def _normalize(extracted: ExtractedConditions, now: datetime) -> NormalizedConditions:
    """필드를 하나씩 본다. 통과하지 못한 값은 고치지 않고 버린다.

    범위는 ``schemas.RecommendRequest``의 제약과 같게 맞춘다. 여기서 걸러내지
    않으면 그쪽에서 ValidationError가 나고, 사용자는 답 대신 422를 본다.
    """
    return NormalizedConditions(
        battery_kwh=_positive(extracted.battery_kwh, high=MAX_BATTERY_KWH),
        soc_now=_in_range(extracted.soc_now, low=0, high=100, include_low=True),
        soc_target=_in_range(extracted.soc_target, low=0, high=100, include_high=True),
        charger_kw=_positive(extracted.charger_kw, high=MAX_CHARGER_KW),
        earliest_start=_moment_value(extracted.earliest_start),
        deadline=_moment_value(extracted.deadline),
        mode=_mode(extracted.mode),
        efficiency=_in_range(extracted.efficiency, low=0, high=1, include_high=True),
        public_base_price=_positive(extracted.public_base_price, high=MAX_PRICE_PER_KWH),
    )


def _positive(value: float | None, *, high: float) -> float | None:
    """0 초과 ``high`` 이하. 상한은 ``RecommendRequest``와 같다 — 여기서 걸러야
    스키마에서 튕겨 모든 항목을 통째로 되묻는 일이 없다."""
    return _in_range(value, low=0, high=high, include_high=True)


def _in_range(
    value: float | None,
    *,
    low: float,
    high: float,
    include_low: bool = False,
    include_high: bool = False,
) -> float | None:
    if value is None:
        return None
    low_ok = value >= low if include_low else value > low
    high_ok = value <= high if include_high else value < high
    return float(value) if low_ok and high_ok else None


def _moment_value(value: str | None) -> datetime | None:
    """ISO 8601 문자열 → KST aware datetime. 읽을 수 없으면 None.

    ``fromisoformat``은 "내일 아침"·"2026-13-45T99:00" 같은 것에 ValueError를
    낸다. 그 경우 그 항목만 "모른다"가 된다 — 대충 오늘 아침으로 찍어 주면
    사용자는 자기가 말하지도 않은 시각에 맞춘 계획을 받는다.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    # 오프셋 없이 오면 KST로 읽는다 — RecommendRequest와 같은 규칙이다.
    return parsed.replace(tzinfo=KST) if parsed.tzinfo is None else parsed.astimezone(KST)


def _mode(value: str | None) -> Mode | None:
    """Literal 3개 중 하나가 아니면 None.

    모르는 값을 그대로 통과시키면 스키마에서 422가 된다. "말하지 않은 것"과
    같게 다뤄 ``RecommendRequest``의 기본값(self_low)이 적용되게 하는 편이,
    사용자가 오류 화면을 보는 것보다 낫다 — ``/api/recommend``에 mode를 빼고
    보냈을 때와 정확히 같은 동작이다.
    """
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned if cleaned in get_args(Mode) else None  # type: ignore[return-value]


def _history_lines(history: list[dict]) -> list[str]:
    """이전 대화를 프롬프트에 붙일 수 있는 줄로.

    ``ChatRequest.history``는 ``list[dict]``라 모양이 보장되지 않는다(프론트가
    보내는 값이다). 아는 모양만 쓰고 나머지는 조용히 버린다 — 여기서 까다롭게
    굴면 대화 이력 하나 때문에 질문 자체가 실패한다.
    """
    lines: list[str] = []
    for turn in history[-6:]:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "user")).strip()
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        speaker = "사용자" if role != "assistant" else "assistant"
        lines.append(f"- {speaker}: {content[:500]}")
    return lines


# ---------------------------------------------------------------------------
# 내부 — 조건 → 요청, 되묻기, 문장
# ---------------------------------------------------------------------------


def _to_request(conditions: NormalizedConditions) -> RecommendRequest | None:
    """``RecommendRequest``를 만들 수 있으면 만든다.

    ``battery_kwh``·``charger_kw``는 비어 있어도 만든다 — 그 둘은 기본 차량이
    채워줄 수 있고(F-12), 그 병합은 DB 세션이 필요해 라우터가 한다.

    ``mode``·``efficiency``는 None이면 **아예 넘기지 않는다.** ``mode=None``을
    넘기면 스키마가 거부하고, 무엇보다 ``model_fields_set``에 들어가 버려서
    ``resolve_vehicle_defaults``가 "사용자가 직접 지정한 값"으로 오해해 차량
    기본값을 덮지 않는다.
    """
    if conditions.soc_now is None or conditions.soc_target is None:
        return None
    if conditions.earliest_start is None or conditions.deadline is None:
        return None

    payload: dict[str, object] = {
        "battery_kwh": conditions.battery_kwh,
        "soc_now": conditions.soc_now,
        "soc_target": conditions.soc_target,
        "charger_kw": conditions.charger_kw,
        "earliest_start": conditions.earliest_start,
        "deadline": conditions.deadline,
    }
    if conditions.mode is not None:
        payload["mode"] = conditions.mode
    if conditions.efficiency is not None:
        payload["efficiency"] = conditions.efficiency
    if conditions.public_base_price is not None:
        payload["public_base_price"] = conditions.public_base_price

    try:
        return RecommendRequest.model_validate(payload)
    except ValidationError:
        # 값 하나하나는 범위 안인데 서로 앞뒤가 안 맞는 경우다
        # (soc_target <= soc_now, deadline <= earliest_start, 14일 초과).
        # 값을 버려 되묻는 쪽으로 보낸다 — 어느 쪽이 틀렸는지 알 수 없으므로
        # 바로잡아 주지 않는다.
        return None


def _missing_fields(
    conditions: NormalizedConditions, *, has_default_vehicle: bool
) -> list[str]:
    """되물어야 할 항목. ``REQUIRED_FIELDS`` 순서를 지켜 답이 흔들리지 않게 한다."""
    missing: list[str] = []
    for name in REQUIRED_FIELDS:
        if getattr(conditions, name) is not None:
            continue
        # 기본 차량이 있으면 이 둘은 채워진다 (F-12). 이미 아는 것을 되묻지 않는다.
        if has_default_vehicle and name in ("battery_kwh", "charger_kw"):
            continue
        missing.append(name)
    if conditions.mode == "public_fast" and conditions.public_base_price is None:
        missing.append(PUBLIC_FAST_PRICE)

    if missing:
        return missing

    # 필수 항목이 다 있는데도 요청을 못 만들었다 = 서로 앞뒤가 안 맞는다.
    # (soc_target <= soc_now 같은 경우) 어느 쪽이 틀렸는지 모르므로 둘 다 되묻는다.
    return _inconsistent_fields(conditions)


def _inconsistent_fields(conditions: NormalizedConditions) -> list[str]:
    fields: list[str] = []
    if (
        conditions.soc_now is not None
        and conditions.soc_target is not None
        and conditions.soc_target <= conditions.soc_now
    ):
        fields.extend(["soc_now", "soc_target"])
    if (
        conditions.earliest_start is not None
        and conditions.deadline is not None
        and conditions.deadline <= conditions.earliest_start
    ):
        fields.extend(["earliest_start", "deadline"])
    if (
        conditions.earliest_start is not None
        and conditions.deadline is not None
        and conditions.deadline - conditions.earliest_start > timedelta(days=14)
    ):
        fields.extend(["earliest_start", "deadline"])
    # 여기까지 와서 아무것도 못 짚으면 스키마가 우리가 모르는 이유로 거부한
    # 것이다. 빈 목록으로 답하면 "뭘 더 달라는 건지" 알 수 없으므로 필수
    # 항목을 통째로 되묻는다.
    return sorted(set(fields), key=REQUIRED_FIELDS.index) or list(REQUIRED_FIELDS)


def _ask_back(missing: list[str]) -> str:
    if not missing:
        # 도달하지 않아야 하지만, 빈 문자열을 내보내는 것보다는 낫다.
        return "질문을 조금 더 자세히 알려주시면 계산해 드릴게요."
    labels = ", ".join(FIELD_LABELS.get(name, name) for name in missing)
    return f"계산하려면 {labels}을(를) 알아야 해요. 알려주시면 바로 계산해 드릴게요."


def _moment(value: datetime, now: datetime) -> str:
    """"오늘(10월 7일) 오후 10시 00분". 오늘·내일·모레면 앞에 붙여 읽기 쉽게 한다.

    상대 표현을 붙여도 날짜는 **항상 함께 적는다.** "내일 오전 3시"만 쓰면
    사용자가 이 답을 나중에 다시 볼 때(대화 기록, 캡처) 어느 날 얘기였는지
    알 수 없다. 괄호로 묶어야 "오늘 10월 7일"처럼 어색하게 읽히지 않는다.
    """
    local = value.astimezone(KST)
    days = (local.date() - now.astimezone(KST).date()).days
    relative = {0: "오늘", 1: "내일", 2: "모레"}.get(days)
    date_label = f"{local.month}월 {local.day}일"
    day_label = f"{relative}({date_label})" if relative else date_label
    meridiem = "오전" if local.hour < 12 else "오후"
    hour12 = local.hour % 12 or 12
    return f"{day_label} {meridiem} {hour12}시 {local.minute:02d}분"
