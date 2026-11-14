"""차량 앱(Pleos Connect)용 엔드포인트. 계약: docs/car-api.md.

차량 앱은 로그인 없이 쓴다. 계산 엔드포인트는 기기 토큰이 없으면 DB를 쓰지 않는다.
기기 토큰과 절감 기록은 ``car_devices``·``car_savings``(BE-5)에 있다.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DbSession

from ...domain.pricing import KST
from ...infra.claude import AnthropicClaudeClient, ClaudeClient
from ...infra.db import get_session
from ...settings import get_settings
from ..car_devices import client_ip, consume_device_quota, issue_device, require_device
from ..car_leak_service import compute_leak_check
from ..car_plan_service import compute_car_plan
from ..car_savings import confirm, summarize, to_out, try_record
from ..car_voice_quota import VoiceQuotaExceededError, consume_voice_quota
from ..car_voice_service import arrival_briefing, converse
from ..deps import get_public_prices
from ..months import month_of
from ..schemas import (
    CarDeviceOut,
    CarLeakCheckRequest,
    CarLeakCheckResponse,
    CarPlanRequest,
    CarPlanResponse,
    CarSavingOut,
    CarSavingsSummary,
    CarVoiceRequest,
    CarVoiceResponse,
)

router = APIRouter(prefix="/api/car", tags=["car"])

VOICE_NOT_READY = "음성 대화는 아직 준비 중이에요."


def now_kst() -> datetime:
    """서버 현재 시각. 테스트가 이 함수를 바꿔 시각을 고정한다."""
    return datetime.now(KST)


@router.post("/plan", response_model=CarPlanResponse)
def car_plan(payload: CarPlanRequest, request: Request) -> CarPlanResponse:
    """가장 싼 충전 구간, 차량 예약 충전에 넣을 값, TTS로 읽을 문장을 돌려준다.

    기기 토큰이 있고 아끼는 돈이 있으면 대기 절감 기록을 만들고 ``saving_id``를 붙인다.
    """
    result = compute_car_plan(payload, now_kst())
    if result.plan is not None and result.savings_won:
        saving_id = try_record(
            request,
            cause="time",
            savings_won=result.savings_won,
            energy_kwh=result.plan.energy_kwh,
            source="plan",
        )
        result = result.model_copy(update={"saving_id": saving_id})
    return result


@router.post("/leak-check", response_model=CarLeakCheckResponse)
def car_leak_check(payload: CarLeakCheckRequest, request: Request) -> CarLeakCheckResponse:
    """충전 중에 돈이 새고 있는지(비싼 시간대·비싼 결제 방식) 알려 준다.

    기기 토큰이 있고 ``leaking=true``면 대기 절감 기록을 만들고 ``saving_id``를 붙인다.
    """
    result = compute_leak_check(
        payload,
        now_kst(),
        min_won=get_settings().car_leak_min_won,
        load_prices=get_public_prices,
    )
    if result.leaking and result.cause is not None:
        saving_id = try_record(
            request,
            cause=result.cause,
            savings_won=result.leak_won,
            energy_kwh=result.energy_kwh,
            source="leak_check",
        )
        result = result.model_copy(update={"saving_id": saving_id})
    return result


@router.post("/devices", response_model=CarDeviceOut, status_code=201)
def register_device(
    request: Request, response: Response, session: DbSession = Depends(get_session)
) -> CarDeviceOut:
    """기기 토큰 발급. 토큰은 이 응답에서 한 번만 보이고 서버는 해시만 저장한다."""
    consume_device_quota(session, client_ip(request), now_kst())
    device_id, token = issue_device(session)
    response.headers["Cache-Control"] = "no-store"
    return CarDeviceOut(device_id=device_id, device_token=token)


@router.post("/savings/{saving_id}/confirm", response_model=CarSavingOut)
def confirm_saving(
    saving_id: str, request: Request, session: DbSession = Depends(get_session)
) -> CarSavingOut:
    """앱이 추천을 실제로 따랐다고 확인한 기록을 확정한다. 다시 불러도 한 번만 센다."""
    device = require_device(request, session)
    saving = confirm(session, device, saving_id, now_kst())
    if saving is None:
        # 없는 기록, 다른 기기의 기록, 20개 상한으로 지워진 대기 기록을 구분하지 않는다.
        raise HTTPException(status_code=404, detail="절감 기록을 찾을 수 없습니다.")
    return to_out(saving)


@router.get("/savings/summary", response_model=CarSavingsSummary)
def savings_summary(
    request: Request,
    month: str | None = Query(None, description="YYYY-MM (KST). 생략하면 이번 달"),
    session: DbSession = Depends(get_session),
) -> CarSavingsSummary:
    """확정된 절감 기록의 이번 달·올해·전체 합계와 시동 때 읽을 문장."""
    device = require_device(request, session)
    now = now_kst()
    summary = summarize(session, device, month or month_of(now), now)
    session.commit()  # last_seen_at
    return summary


def anthropic_api_key() -> str:
    """설정의 Claude 키. 테스트가 ``dependency_overrides``로 "키 있음/없음"을 정한다."""
    return get_settings().anthropic_api_key


def claude_client() -> ClaudeClient:
    """실제 호출기. 테스트는 여기에 가짜를 꽂는다. SDK 클라이언트는 첫 호출에서 만든다."""
    settings = get_settings()
    return AnthropicClaudeClient(api_key=settings.anthropic_api_key, model=settings.claude_model)


def _spoken_error(status_code: int, speech: str, headers: dict[str, str] | None = None):
    """음성 대화의 오류 본문. ``detail`` 옆에 TTS로 읽을 ``speech``를 같은 문장으로 둔다."""
    return JSONResponse(
        status_code=status_code, content={"detail": speech, "speech": speech}, headers=headers
    )


@router.post(
    "/voice",
    response_model=CarVoiceResponse,
    responses={
        401: {"description": "기기 토큰이 없거나 틀림"},
        429: {"description": "기기별 또는 서비스 전체 하루 한도 초과 ({detail, speech})"},
        501: {"description": "ANTHROPIC_API_KEY 미설정 ({detail, speech})"},
    },
)
def car_voice(
    payload: CarVoiceRequest,
    request: Request,
    session: DbSession = Depends(get_session),
    api_key: str = Depends(anthropic_api_key),
    client: ClaudeClient = Depends(claude_client),
):
    """음성 대화. 순서: 기기 토큰(401) → 귀가길 브리핑 첫 질문(200) → 키(501) → 한도(429).

    Claude 오류·시간 초과는 200과 서버 문장(``fallback=true``)이다. 운전 중 화면에 오류를
    띄우지 않는다.
    """
    device = require_device(request, session)
    session.commit()  # last_seen_at
    now = now_kst()
    if payload.text is None:
        return arrival_briefing(payload.context)
    if not api_key:
        return _spoken_error(501, VOICE_NOT_READY)
    try:
        consume_voice_quota(session, device, now)
    except VoiceQuotaExceededError as exc:
        return _spoken_error(
            429,
            exc.speech,
            {"Retry-After": str(exc.retry_after), "X-RateLimit-Scope": exc.scope},
        )
    return converse(client, payload, session=session, device=device, now=now)
