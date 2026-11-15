"""와트잇 시동 ON 한 줄 브리핑 (BE-9). 계약은 ``docs/car-api.md`` "시동 ON 브리핑" 절.

시동을 켤 때 한 번 읽을 최대 3문장. 새 계산은 없고 기존 서비스를 모은다.

- ``price``: 지금 요금 구간과 단가, 오늘 다음으로 싸지는 시각, 오늘 주말·공휴일 할인 구간
  (``domain/pricing.py``의 ``price_at``·``hourly_prices``, ``/api/timeline``과 같은 값)
- ``tonight``: 잔량이 ``CAR_BRIEFING_LOW_SOC`` 미만이면 오늘 밤 최저 예약 구간과 아끼는 금액
  (BE-1 ``compute_car_plan``). 출발은 이 기기의 평소 출발 시각(BE-8, high)이 있으면 그 시각,
  없으면 오전 8시 가정이고 문장에 밝힌다.
- ``savings``: 기기 토큰이 있고 이번 달 확정 절감이 있으면 이번 달·올해 합계(BE-5 ``summarize``)

문장 우선순위는 tonight > price > savings이고, 읽는 순서는 price → tonight → savings다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from ..domain.departures import DepartureSuggestion
from ..domain.errors import DomainError, InsufficientTimeError
from ..domain.pricing import KST, hourly_prices, price_at
from ..infra.db import session_scope
from .car_departures import error_kind, suggestion_for
from .car_devices import bearer_token, find_device
from .car_leak_service import DEFAULT_DEPART_TIME, assumed_depart_note
from .car_plan_service import (
    compute_car_plan,
    spoken_clock,
    spoken_moment,
    spoken_percent,
)
from .car_savings import summarize
from .deps import get_holidays, get_tariff
from .months import month_of
from .schemas import (
    BriefingPrice,
    BriefingSavings,
    BriefingTonight,
    BriefingWindow,
    CarBriefingRequest,
    CarBriefingResponse,
    CarPlanRequest,
    CarSavingsSummary,
    SetReservationAction,
)

logger = logging.getLogger(__name__)

MAX_SENTENCES = 3
# 이 시각 전에 시동을 켜면 "오늘 밤"은 지금 지나고 있는 밤이고 출발은 오늘 아침이다.
# 그 뒤에 켜면(아침 출근, 낮, 저녁 귀가) 다음 충전은 다가오는 밤이고 출발은 내일이다.
NIGHT_END_HOUR = 4
# 같은 기기가 이 시간 안에 같은 계획으로 다시 부르면 대기 절감 기록을 새로 만들지 않는다.
REUSE_WINDOW = timedelta(minutes=10)

BAND_LABELS = {"light": "경부하", "middle": "중간부하", "peak": "최대부하"}
BAND_PHRASES = {
    "light": "요금이 싼 시간",
    "middle": "요금이 중간인 시간",
    "peak": "요금이 비싼 시간",
}
# "오늘 밤 충전"은 집에 와서 꽂는 충전이다. 시동을 켠 지금은 차가 움직이므로, 저녁 전에
# 켰으면 이 시각부터 꽂을 수 있다고 보고 계획한다. 그래야 낮 시간(봄·가을 주말 할인 등)을
# "오늘 밤" 예약으로 고르지 않고, 아끼는 금액도 "꽂자마자 충전"과 비교한 값이 된다.
EVENING_PLUG_IN = time(18, 0)


@dataclass(frozen=True)
class Personal:
    """기기 토큰이 맞을 때만 있는 개인화 값."""

    usual: DepartureSuggestion | None
    summary: CarSavingsSummary | None


@dataclass(frozen=True)
class Briefing:
    response: CarBriefingResponse
    # 대기 절감 기록에 쓸 값(아끼는 돈이 있을 때만)
    record_won: int = 0
    record_energy_kwh: float = 0.0


def tonight_departure_day(now: datetime) -> date:
    """오늘 밤 충전을 마쳐야 하는 출발의 날짜."""
    local = now.astimezone(KST)
    return local.date() if local.hour < NIGHT_END_HOUR else local.date() + timedelta(days=1)


def tonight_plug_in(now: datetime) -> datetime:
    """오늘 밤 충전을 시작할 수 있는 가장 이른 시각. 새벽(04시 전)과 저녁 6시 이후는 지금."""
    local = now.astimezone(KST)
    if local.hour < NIGHT_END_HOUR:
        return local
    return max(local, datetime.combine(local.date(), EVENING_PLUG_IN, tzinfo=KST))


def load_personal(request: Request, now: datetime) -> Personal | None:
    """토큰이 없으면 DB를 열지 않는다. 틀리거나 DB가 실패하면 None(계산은 그대로)."""
    token = bearer_token(request)
    if token is None:
        return None
    try:
        with session_scope(request.app.dependency_overrides) as session:
            device = find_device(session, token)
            if device is None:
                return None
            try:
                usual = suggestion_for(session, device, tonight_departure_day(now), get_holidays())
            except DomainError:
                usual = None
            summary = summarize(session, device, month_of(now), now)
            session.commit()  # last_seen_at
    except SQLAlchemyError as exc:
        logger.warning("브리핑 개인화 값을 읽지 못했습니다 (%s)", error_kind(exc))
        return None
    return Personal(usual=usual, summary=summary)


def compute_briefing(
    payload: CarBriefingRequest, now: datetime, *, low_soc: float, personal: Personal | None
) -> Briefing:
    now = now.astimezone(KST)
    tariff = get_tariff()
    price = briefing_price(now, payload.mode)
    price_sentence = compose_price_sentence(price, now)
    tonight, tonight_sentences, assumptions, plan = _tonight(payload, now, low_soc, personal)

    savings = None
    savings_sentences: list[str] = []
    summary = personal.summary if personal is not None else None
    if summary is not None and summary.month_won > 0:
        savings = BriefingSavings(
            month=summary.month,
            month_won=summary.month_won,
            year=summary.year,
            year_won=summary.year_won,
        )
        savings_sentences = [summary.speech]

    speech = compose_speech(price_sentence, tonight_sentences, savings_sentences)
    actions = (
        [
            SetReservationAction(
                start_hhmm=tonight.reservation.start_hhmm, end_hhmm=tonight.reservation.end_hhmm
            )
        ]
        if tonight.reservation is not None
        else []
    )
    response = CarBriefingResponse(
        price=price,
        tonight=tonight,
        savings=savings,
        speech=speech,
        actions=actions,
        assumptions=assumptions,
        unverified_tariff_items=tariff.unverified_items(),
    )
    if plan is None:
        return Briefing(response)
    return Briefing(response, record_won=plan[0], record_energy_kwh=plan[1])


def compose_speech(price: str, tonight: list[str], savings: list[str]) -> str:
    """최대 3문장.

    고르는 순서는 tonight > price > savings, 읽는 순서는 price → tonight → savings다.
    """
    budget = MAX_SENTENCES
    chosen_tonight = tonight[:budget]
    budget -= len(chosen_tonight)
    chosen_price = [price][:budget]
    budget -= len(chosen_price)
    chosen_savings = savings[:budget]
    return " ".join(chosen_price + chosen_tonight + chosen_savings)


# ---------------------------------------------------------------------------
# price
# ---------------------------------------------------------------------------


def briefing_price(now: datetime, mode: str) -> BriefingPrice:
    tariff, holidays = get_tariff(), get_holidays()
    local = now.astimezone(KST)
    today = local.date()
    current = price_at(local, mode, tariff, holidays)  # type: ignore[arg-type]
    hours = hourly_prices(today, mode, tariff, holidays)  # type: ignore[arg-type]
    cheaper = next(
        (h for h in hours if h.hour > local.hour and h.price_per_kwh < current.price_per_kwh),
        None,
    )
    discounted = [h.hour for h in hours if h.discounted]
    window = (
        BriefingWindow(
            start_at=_at(today, discounted[0]),
            end_at=_at(today, discounted[-1]) + timedelta(hours=1),
        )
        if discounted
        else None
    )
    return BriefingPrice(
        band=current.band,
        band_label=BAND_LABELS[current.band],
        price_per_kwh=current.price_per_kwh,
        discounted=current.discounted,
        next_cheaper_at=_at(today, cheaper.hour) if cheaper is not None else None,
        next_cheaper_price_per_kwh=cheaper.price_per_kwh if cheaper is not None else None,
        discount_window=window,
    )


def _at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=KST)


def compose_price_sentence(price: BriefingPrice, now: datetime) -> str:
    """ "지금은 요금이 비싼 시간이고, 밤 10시부터 싸져요." 같은 한 문장."""
    if price.discounted:
        kind = "공휴일" if get_holidays().is_holiday(now.date()) and now.weekday() < 5 else "주말"
        head = f"지금은 {kind} 할인 시간"
    else:
        head = f"지금은 {BAND_PHRASES[price.band]}"
    if price.next_cheaper_at is not None:
        more = "더 " if price.discounted or price.band == "light" else ""
        return f"{head}이고, {spoken_clock(price.next_cheaper_at)}부터 {more}싸져요."
    if price.discounted:
        return f"{head}이라 요금이 싸요."
    return f"{head}이에요."


# ---------------------------------------------------------------------------
# tonight
# ---------------------------------------------------------------------------

_PERIODS = frozenset({"새벽", "오전", "낮", "오후", "저녁", "밤"})


def night_range(start: datetime, end: datetime) -> str:
    """ "저녁 8시 55분부터 새벽 5시 10분까지", "밤 10시부터 11시 19분까지".

    시동 브리핑은 3문장·약 120자 안에 들어가야 해서 ``spoken_range``의 날("오늘", "내일")을
    뺀다. 앞 문장이 "오늘 밤 충전하세요"이고 예약은 출발 전 한 번(24시간 미만, 실제로는 꽂는
    시각부터 다음 아침 출발까지 16시간 안)이라 날이 없어도 헷갈리지 않는다. 끝 시각의 때가
    시작과 같으면 뺀다.
    """
    start_text, end_text = spoken_clock(start), spoken_clock(end)
    start_period, *end_rest = start_text.split()[0], *end_text.split()[1:]
    if end_text.split()[0] == start_period and start_period in _PERIODS and end_rest:
        end_text = " ".join(end_rest)
    return f"{start_text}부터 {end_text}까지"


def _tonight(
    payload: CarBriefingRequest, now: datetime, low_soc: float, personal: Personal | None
) -> tuple[BriefingTonight, list[str], list[str], tuple[int, float] | None]:
    """(응답 항목, 문장, 가정, 기록할 (금액, 전력량))."""
    percent = spoken_percent(payload.soc_now)
    if payload.soc_now >= low_soc:
        return (
            BriefingTonight(needs_charging=False, soc_now=payload.soc_now, low_soc=low_soc),
            [f"배터리가 {percent}라 오늘 밤은 충전 안 해도 돼요."],
            [],
            None,
        )

    day = tonight_departure_day(now)
    usual = personal.usual if personal is not None else None
    if (
        usual is not None
        and usual.target == day
        and usual.confidence == "high"
        and usual.depart_at is not None
        and usual.depart_at > now
    ):
        depart_at, basis = usual.depart_at, "usual"
    else:
        usual = None
        depart_at, basis = datetime.combine(day, DEFAULT_DEPART_TIME, tzinfo=KST), "default"
    assumptions = [assumed_depart_note(depart_at, usual)]
    plug_in_at = tonight_plug_in(now)
    if plug_in_at > now:
        assumptions.append(f"충전기는 오늘 {spoken_clock(plug_in_at)} 이후에 꽂는다고 가정")
    ask = f"배터리가 {percent}라 오늘 밤 충전하세요."
    tonight = BriefingTonight(
        needs_charging=True,
        soc_now=payload.soc_now,
        low_soc=low_soc,
        depart_at=depart_at,
        depart_basis=basis,  # type: ignore[arg-type]
    )

    try:
        result = compute_car_plan(
            CarPlanRequest(
                soc_now=payload.soc_now,
                battery_capacity_wh=payload.battery_capacity_wh,
                charger_kw=payload.charger_kw,
                plug_in_at=plug_in_at,
                depart_at=depart_at,
                mode=payload.mode,
            ),
            now,
        )
    except InsufficientTimeError:
        # 새벽에 켰는데 출발까지 다 채울 시간이 없다. 안전이 먼저라 바로 충전하라고 한다.
        return tonight, [ask, "출발 전까지 채우려면 도착하자마자 충전해 주세요."], assumptions, None
    except DomainError as exc:
        # 내일 날짜의 공휴일 정보가 없는 연말 등: 오늘 밤 계획만 빼고 나머지는 200으로 답한다.
        # 잔량이 낮다는 말은 계산 없이 할 수 있고 편의(충전 실패 막기)가 먼저라 남긴다.
        return (
            tonight.model_copy(update={"depart_at": None, "depart_basis": None}),
            [ask],
            [f"오늘 밤 충전 계획을 계산하지 못했어요: {exc}"],
            None,
        )

    assumptions = assumptions + result.assumptions
    if not result.needs_charging or result.plan is None:
        # 목표 잔량(80%)보다 높은데 CAR_BRIEFING_LOW_SOC를 그 위로 올린 경우
        return (
            BriefingTonight(needs_charging=False, soc_now=payload.soc_now, low_soc=low_soc),
            [f"배터리가 {percent}라 오늘 밤은 충전 안 해도 돼요."],
            [],
            None,
        )

    won = result.savings_won or 0
    tonight = tonight.model_copy(
        update={
            "reservation": result.reservation,
            "savings_won": won,
            "energy_kwh": result.plan.energy_kwh,
        }
    )
    usual_word = "평소처럼 " if usual is not None else ""
    lead = f"{usual_word}{spoken_moment(depart_at, now)} 출발 기준으로"
    if result.reservation is None:
        plan_sentence = (
            f"{lead} 충전에 24시간 넘게 걸려 예약 한 번으로는 맞출 수 없어요. "
            "도착하면 바로 충전해 주세요."
        )
    else:
        start = result.reservation.start_at.astimezone(KST)
        end = result.reservation.end_at.astimezone(KST)
        tail = f"예약하면 약 {won:,}원 아껴요." if won > 0 else "예약하세요."
        plan_sentence = f"{lead} {night_range(start, end)} {tail}"
    return tonight, [ask, plan_sentence], assumptions, (won, result.plan.energy_kwh)
