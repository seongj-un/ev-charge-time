"""``POST /api/car/plan`` 계산과 TTS 문장 (차량 앱 BE-1).

계산은 ``recommend_service.compute_recommendation``을 그대로 쓴다. 여기서 하는
일은 차량이 주는 값을 추천 요청으로 옮기고(Wh → kWh, 도착 → 시작 가능 시각,
출발 → 완료 시각), 결과를 차량 예약 충전 값과 읽을 문장으로 바꾸는 것뿐이다.

서버와 앱은 충전을 직접 켜고 끄지 않는다. 시동이 꺼지면 서드파티 앱은 동작할
수 없으므로, 실제 충전은 차량 기본 예약 충전이 한다 ("계산은 앱이, 실행은 차가").

문장의 숫자(시각, 금액, 잔량)는 전부 계산 결과나 요청 값에서 그대로 온다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.exceptions import RequestValidationError

from ..domain.pricing import KST
from ..domain.reservation import build_reservation, round_window
from .deps import get_tariff
from .recommend_service import compute_recommendation
from .schemas import (
    MAX_REQUEST_SPAN,
    CarPlanRequest,
    CarPlanResponse,
    RecommendRequest,
    ReservationOut,
)


def compute_car_plan(payload: CarPlanRequest, now: datetime) -> CarPlanResponse:
    """차량 충전 계획. ``now``는 KST aware 서버 현재 시각이다.

    ``plug_in_at``이 없거나 이미 지났으면 ``now``를 쓴다. 지난 시각부터 계산하면
    예약 시작이 지금보다 앞서고, 실제 충전은 지금부터라 그만큼 덜 찬다.
    ``depart_at``이 지금 이전이거나 꽂는 시각 이전이면 422다. 충전이 필요 없는
    요청도 이 검사는 거친다 — 출발 시각이 이상한 요청을 \"충전 필요 없음\"으로
    넘기지 않는다.
    """
    now = now.astimezone(KST)
    plug_in_at = max(payload.plug_in_at or now, now)
    _check_window(payload, plug_in_at, now)

    tariff = get_tariff()
    if payload.soc_target <= payload.soc_now:
        return CarPlanResponse(
            needs_charging=False,
            speech=compose_no_charge_speech(payload.soc_now, payload.soc_target),
            assumptions=[],
            unverified_tariff_items=tariff.unverified_items(),
        )

    result = compute_recommendation(
        RecommendRequest(
            battery_kwh=payload.battery_capacity_wh / 1000,
            soc_now=payload.soc_now,
            soc_target=payload.soc_target,
            charger_kw=payload.charger_kw,
            earliest_start=plug_in_at,
            deadline=payload.depart_at,
            mode=payload.mode,
        ),
        tariff,
    )

    best = result.best
    reservation = build_reservation(best.start, best.end, plug_in_at)
    window = round_window(best.start, best.end, plug_in_at)
    arriving = payload.plug_in_at is not None and payload.plug_in_at > now

    return CarPlanResponse(
        needs_charging=True,
        plan=best,
        baseline_now=result.baseline_now,
        savings_won=result.savings_won,
        reservation=(
            ReservationOut(
                start_at=reservation.start_at,
                end_at=reservation.end_at,
                start_hhmm=reservation.start_hhmm,
                end_hhmm=reservation.end_hhmm,
            )
            if reservation is not None
            else None
        ),
        speech=compose_plan_speech(
            window=window,
            savings_won=result.savings_won,
            reservable=reservation is not None,
            arriving=arriving,
            now=now,
        ),
        assumptions=result.assumptions,
        unverified_tariff_items=result.unverified_tariff_items,
    )


def _check_window(payload: CarPlanRequest, plug_in_at: datetime, now: datetime) -> None:
    """``plug_in_at``은 ``now``로 당긴 뒤의 값이다. 오류 문장은 실제로 쓴 기준을 말한다."""
    if payload.depart_at <= now:
        _reject("depart_at", "depart_at은 현재 시각보다 뒤여야 합니다.", payload.depart_at)
    from_now = plug_in_at == now
    if payload.depart_at <= plug_in_at:
        _reject("depart_at", "depart_at은 plug_in_at보다 뒤여야 합니다.", payload.depart_at)
    if payload.depart_at - plug_in_at > MAX_REQUEST_SPAN:
        start = "현재 시각" if from_now else "plug_in_at"
        _reject(
            "depart_at",
            f"{start}과 depart_at 사이는 {MAX_REQUEST_SPAN.days}일을 넘을 수 없습니다.",
            payload.depart_at,
        )


def _reject(field: str, message: str, value: datetime) -> None:
    """FastAPI 기본 검증 오류와 같은 모양(``detail`` 배열)의 422를 낸다."""
    raise RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", field),
                "msg": message,
                "input": value.isoformat(),
            }
        ]
    )


# ---------------------------------------------------------------------------
# TTS 문장
# ---------------------------------------------------------------------------


def compose_plan_speech(
    *,
    window: tuple[datetime, datetime],
    savings_won: int,
    reservable: bool,
    arriving: bool,
    now: datetime,
) -> str:
    """충전 계획을 읽을 문장. 시각은 차량에 넣을 분 단위 값(``window``)을 쓴다.

    ``arriving``은 꽂는 시각이 아직 오지 않았다는 뜻이다 (도착 전 브리핑).
    """
    start, end = (moment.astimezone(KST) for moment in window)
    sentences = [f"{spoken_range(start, end, now)} 충전하면 가장 쌉니다."]

    if savings_won > 0:
        compared = "도착하자마자 충전하는 것보다" if arriving else "지금 바로 충전하는 것보다"
        sentences.append(f"{compared} 약 {savings_won:,}원 아낍니다.")
    else:
        sentences.append("바로 충전해도 요금 차이가 없습니다.")

    if reservable:
        when = "도착하면 " if arriving else ""
        sentences.append(
            f"{when}차량 예약 충전을 {spoken_clock(start)} 시작, "
            f"{spoken_clock(end)} 종료로 설정해 주세요."
        )
    else:
        sentences.append(
            "충전에 24시간 넘게 걸려 차량 예약 충전 한 번으로는 설정할 수 없습니다."
        )
    return " ".join(sentences)


def compose_no_charge_speech(soc_now: float, soc_target: float) -> str:
    return (
        f"잔량 {_percent(soc_now)}가 목표 {_percent(soc_target)} 이상이라 "
        "충전하지 않아도 됩니다."
    )


def spoken_range(start: datetime, end: datetime, now: datetime) -> str:
    """\"오늘 밤 10시부터 내일 새벽 1시까지\", \"내일 새벽 1시부터 5시 30분까지\".

    끝 시각은 시작과 날이 같으면 날을, 날과 때(새벽·오전…)가 모두 같으면 때도
    뺀다.
    """
    start_day, start_period = _day_label(start, now), _period(start)
    end_day, end_period = _day_label(end, now), _period(end)

    end_parts = []
    if end_day != start_day:
        end_parts.append(end_day)
    if end_day != start_day or end_period != start_period:
        end_parts.append(end_period)
    end_parts.append(_clock_only(end))

    start_text = f"{start_day} {spoken_clock(start)}"
    return f"{start_text}부터 {' '.join(end_parts)}까지"


def spoken_clock(moment: datetime) -> str:
    """\"새벽 1시\", \"오후 3시 15분\", \"밤 12시\". 날짜는 붙이지 않는다."""
    return f"{_period(moment)} {_clock_only(moment)}"


def _period(moment: datetime) -> str:
    """하루를 귀로 듣기 쉬운 때로 나눈다. 00:00은 전날 \"밤 12시\"로 읽는다."""
    hour = moment.hour
    if moment.hour == 0 and moment.minute == 0:
        return "밤"
    if hour < 6:
        return "새벽"
    if hour < 12:
        return "오전"
    if hour == 12:
        return "낮"
    if hour < 18:
        return "오후"
    if hour < 21:
        return "저녁"
    return "밤"


def _clock_only(moment: datetime) -> str:
    hour12 = moment.hour % 12 or 12
    return f"{hour12}시 {moment.minute}분" if moment.minute else f"{hour12}시"


def _day_label(moment: datetime, now: datetime) -> str:
    """오늘·내일·모레, 그 밖에는 \"11월 18일\". 00:00은 전날로 센다 (밤 12시)."""
    local = moment.astimezone(KST)
    if local.hour == 0 and local.minute == 0:
        local -= timedelta(minutes=1)
    days = (local.date() - now.astimezone(KST).date()).days
    relative = {0: "오늘", 1: "내일", 2: "모레"}.get(days)
    return relative or f"{local.month}월 {local.day}일"


def _percent(value: float) -> str:
    """85.0 → \"85%\", 32.46 → \"32.5%\". 요청 값을 소수 첫째 자리까지만 읽는다."""
    return f"{round(value, 1):g}%"
