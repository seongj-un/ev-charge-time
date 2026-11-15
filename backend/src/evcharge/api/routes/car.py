"""차량 앱(Pleos Connect)용 엔드포인트. 계약: docs/car-api.md.

차량 앱은 로그인 없이 쓴다. 계산 엔드포인트는 기기 토큰이 없으면 DB를 쓰지 않는다.
기기 토큰과 절감 기록은 ``car_devices``·``car_savings``(BE-5)에 있다.
"""

import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DbSession

from ...domain.departures import DepartureSuggestion
from ...domain.errors import DomainError
from ...domain.pricing import KST
from ...infra.claude import AnthropicClaudeClient, ClaudeClient
from ...infra.db import get_session
from ...infra.models import CarDevice
from ...settings import get_settings
from ..car_briefing_service import REUSE_WINDOW, compute_briefing, load_personal
from ..car_departures import (
    DepartureLimitError,
    check_observed_time,
    delete_departures,
    next_usual_departure,
    raise_limit,
    record_departure,
    suggestion_for,
    to_suggestion_out,
    try_record_stated,
    usual_departure_for,
)
from ..car_devices import (
    client_ip,
    consume_device_quota,
    ip_key,
    issue_device,
    require_device,
)
from ..car_leak_service import compute_leak_check
from ..car_plan_service import compute_car_plan
from ..car_route_service import find_along_route
from ..car_savings import confirm, summarize, to_out, try_record
from ..car_target_service import compute_charge_target
from ..car_voice_quota import VoiceQuotaExceededError, consume_voice_quota
from ..car_voice_service import arrival_briefing, check_arrival_at, converse
from ..deps import get_holidays, get_public_prices
from ..months import month_of
from ..schemas import (
    CarBriefingRequest,
    CarBriefingResponse,
    CarChargeTargetRequest,
    CarChargeTargetResponse,
    CarDepartureIn,
    CarDepartureOut,
    CarDeparturesDeleted,
    CarDepartureSuggestion,
    CarDeviceOut,
    CarLeakCheckRequest,
    CarLeakCheckResponse,
    CarPlanRequest,
    CarPlanResponse,
    CarRouteChargersRequest,
    CarRouteChargersResponse,
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
    now = now_kst()
    result = compute_car_plan(payload, now)
    # 운전자가 정한 출발 시각을 출발 학습에 남긴다(토큰이 있을 때만, 응답은 그대로).
    try_record_stated(request, payload.depart_at, now)
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


@router.post("/briefing", response_model=CarBriefingResponse)
def car_briefing(payload: CarBriefingRequest, request: Request) -> CarBriefingResponse:
    """시동 ON 한 줄 브리핑(최대 3문장): 지금 요금, 오늘 밤 충전, 이번 달 절약.

    기기 토큰은 선택이다. 없거나 틀리면 개인화 값(평소 출발 시각, 절약 합계)만 빠지고 계산은
    같다. 아끼는 돈이 있으면 대기 절감 기록을 만들고(기기당 브리핑 대기 기록은 하나), 10분 안 같은
    계획이면 그 기록을 다시 준다.
    """
    now = now_kst()
    personal = load_personal(request, now)
    briefing = compute_briefing(
        payload, now, low_soc=get_settings().car_briefing_low_soc, personal=personal
    )
    result = briefing.response
    if briefing.record_won > 0:
        saving_id = try_record(
            request,
            cause="time",
            savings_won=briefing.record_won,
            energy_kwh=briefing.record_energy_kwh,
            source="briefing",
            reuse_within=REUSE_WINDOW,
            single=True,
        )
        result = result.model_copy(update={"saving_id": saving_id})
    return result


@router.post("/leak-check", response_model=CarLeakCheckResponse)
def car_leak_check(payload: CarLeakCheckRequest, request: Request) -> CarLeakCheckResponse:
    """충전 중에 돈이 새고 있는지(비싼 시간대·비싼 결제 방식) 알려 준다.

    기기 토큰이 있고 ``leaking=true``면 대기 절감 기록을 만들고 ``saving_id``를 붙인다.
    """
    now = now_kst()
    # 출발 시각이 없으면 평소 출발 시각(high)을 가정에 쓴다. 토큰이 없으면 DB를 열지 않는다.
    usual = (
        usual_departure_for(request, now)
        if payload.place == "home" and payload.depart_at is None
        else None
    )
    result = compute_leak_check(
        payload,
        now,
        min_won=get_settings().car_leak_min_won,
        load_prices=get_public_prices,
        usual=usual,
    )
    if payload.place == "home" and payload.depart_at is not None:
        # 받은 출발 시각만 남긴다. 서버가 가정한 시각은 남기지 않는다.
        try_record_stated(request, payload.depart_at, now)
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


@router.post("/charge-target", response_model=CarChargeTargetResponse)
def charge_target(payload: CarChargeTargetRequest) -> CarChargeTargetResponse:
    """몇 %까지 채우면 되는지 (BE-11). 공개 계산 API: 기기 토큰도 DB도 쓰지 않는다."""
    return compute_charge_target(payload)


@router.post("/chargers/along-route", response_model=CarRouteChargersResponse)
def chargers_along_route(
    payload: CarRouteChargersRequest, session: DbSession = Depends(get_session)
) -> CarRouteChargersResponse:
    """경로 근처에서 지금 비어 있는 급속 충전기를 경로 순서대로 (BE-7). 공개 계산 API.

    경로는 origin → route_points → destination 꺾은선 근사다(도로 경로가 아님).
    """
    return find_along_route(session, payload, now_kst())


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


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_ERROR = "date는 YYYY-MM-DD 형식이어야 합니다."


@router.post("/departures", response_model=CarDepartureOut, status_code=201)
def record_observed_departure(
    payload: CarDepartureIn,
    request: Request,
    response: Response,
    session: DbSession = Depends(get_session),
) -> CarDepartureOut:
    """집 출발 기록(기어가 P에서 벗어난 첫 시각). 30분 안 중복은 합치고 200을 준다."""
    device = require_device(request, session)
    now = now_kst()
    check_observed_time(payload.departed_at, now)
    try:
        departure, created = record_departure(
            session, device, payload.departed_at, payload.source, now
        )
    except DepartureLimitError as exc:
        raise_limit(exc)
        raise  # raise_limit가 늘 던진다
    if not created:
        response.status_code = 200
    return CarDepartureOut(
        departure_id=departure.id,
        departed_at=departure.departed_at,
        source=departure.source,
        merged=not created,
    )


@router.delete("/departures", response_model=CarDeparturesDeleted)
def delete_all_departures(
    request: Request, session: DbSession = Depends(get_session)
) -> CarDeparturesDeleted:
    """이 기기의 출발 기록(observed, stated)을 전부 지운다."""
    device = require_device(request, session)
    return CarDeparturesDeleted(deleted=delete_departures(session, device))


@router.get("/departures/suggest", response_model=CarDepartureSuggestion)
def suggest_departure(
    request: Request,
    date_param: str | None = Query(
        None, alias="date", description="YYYY-MM-DD (KST). 생략하면 내일"
    ),
    session: DbSession = Depends(get_session),
) -> CarDepartureSuggestion:
    """그날의 평소 출발 시각 제안. 기록이 3건 미만이면 시각과 신뢰도가 null이다."""
    device = require_device(request, session)
    now = now_kst()
    target = _parse_date(date_param) if date_param is not None else (
        now.astimezone(KST).date() + timedelta(days=1)
    )
    found = suggestion_for(session, device, target, get_holidays())
    session.commit()  # last_seen_at
    return to_suggestion_out(found, now)


def _parse_date(value: str) -> date:
    if not _DATE_RE.match(value):
        raise HTTPException(status_code=422, detail=_DATE_ERROR)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_DATE_ERROR) from exc
    if not 1970 <= parsed.year <= 9998:
        raise HTTPException(status_code=422, detail="date는 1970년부터 9998년 사이여야 합니다.")
    return parsed


def anthropic_api_key() -> str:
    """설정의 Claude 키. 테스트가 ``dependency_overrides``로 "키 있음/없음"을 정한다."""
    return get_settings().anthropic_api_key


def claude_client() -> ClaudeClient:
    """실제 호출기. 테스트는 여기에 가짜를 꽂는다. SDK 클라이언트는 첫 호출에서 만든다."""
    settings = get_settings()
    return AnthropicClaudeClient(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
        workspace_id=settings.claude_workspace_id,
    )


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
    """음성 대화. 순서: 기기 토큰(401) → 귀가길 브리핑 첫 질문(200) → 키(501)
    → 하루 한도(429, 기기 → IP → 서비스).

    Claude 오류·시간 초과는 200과 서버 문장(``fallback=true``)이다. 운전 중 화면에 오류를
    띄우지 않는다.
    """
    device = require_device(request, session)
    session.commit()  # last_seen_at
    now = now_kst()
    check_arrival_at(payload.context, now)
    usual = _usual_departure(session, device, now)
    if payload.text is None:
        return arrival_briefing(payload.context, usual, now)
    if not api_key:
        return _spoken_error(501, VOICE_NOT_READY)
    try:
        consume_voice_quota(session, device, ip_key(client_ip(request)), now)
    except VoiceQuotaExceededError as exc:
        return _spoken_error(
            429,
            exc.speech,
            {"Retry-After": str(exc.retry_after), "X-RateLimit-Scope": exc.scope},
        )
    return converse(client, payload, session=session, device=device, now=now, usual=usual)


def _usual_departure(
    session: DbSession, device: CarDevice, now: datetime
) -> DepartureSuggestion | None:
    """평소 출발 시각 제안(high/low). 계산할 수 없으면 None이고 대화는 지금처럼 간다."""
    try:
        holidays = get_holidays()
    except DomainError:
        return None
    return next_usual_departure(session, device, now, holidays)
