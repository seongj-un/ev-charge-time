"""``POST /api/car/leak-check`` "돈이 새고 있어요" 알림 (와트잇 BE-4).

앱은 차가 충전 중일 때 이 API를 부른다. 서버는 지금 충전 방식으로 새는 돈을
계산해, 기준(settings ``car_leak_min_won``) 이상이면 할 일을 알려 주는 짧은 문장을
돌려준다. 서버는 충전을 켜거나 끄지 않는다.

돈이 새는 원인은 둘이다.

- ``place="home"`` (집·회사 완속): 시간대. 지금 바로 충전 vs 출발 전 최저 구간.
  계산과 시각 검증은 ``car_plan_service.compute_car_plan``을 그대로 쓴다.
- ``place="public"`` (공공 충전기): 결제 방식. 로밍가·비회원가 vs 회원가.
  한국소비자원 20개 사업자 평균 단가(``config/public_charging_prices.yaml``)로
  추정한다. 공공 충전기는 시간대 계산을 하지 않는다 (공공 급속 기준단가 미확인).

문장의 숫자는 전부 계산값이나 요청 값이다.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from ..domain.errors import InsufficientTimeError
from ..domain.pricing import KST
from ..domain.public_prices import PublicPrices
from .car_plan_service import (
    compute_car_plan,
    reject_field,
    spoken_clock,
    spoken_moment,
    spoken_percent,
)
from .schemas import (
    CarLeakCheckRequest,
    CarLeakCheckResponse,
    CarPlanRequest,
)

# depart_at이 없을 때 가정하는 출발 시각 (KST).
DEFAULT_DEPART_TIME = time(8, 0)

PAYMENT_LABELS = {"roaming": "로밍가", "nonmember": "비회원가"}
SPEED_LABELS = {"slow": "완속", "fast": "급속"}

OK_SPEECH = "지금 충전해도 괜찮아요."
PUBLIC_ASSUMPTIONS: tuple[str, ...] = (
    "한국소비자원 2025-12-17 발표 20개 사업자 평균 단가 기준 추정",
    "이 충전소 사업자의 실제 요금과 다를 수 있음",
    "기본요금 제외, kWh당 요금만 계산",
)


def default_depart_at(now: datetime) -> datetime:
    """지금 다음에 처음 오는 오전 8시 (KST).

    저녁에 충전 중이면 다음 날 8시, 0시~8시 사이면 그날 8시다. 새벽 1시에 충전 중인
    운전자의 "다음 출발"을 31시간 뒤로 잡으면 다음 날 밤 구간을 고르게 된다.
    """
    local = now.astimezone(KST)
    candidate = datetime.combine(local.date(), DEFAULT_DEPART_TIME, tzinfo=KST)
    return candidate if candidate > local else candidate + timedelta(days=1)


def compute_leak_check(
    payload: CarLeakCheckRequest, now: datetime, *, min_won: int, prices: PublicPrices
) -> CarLeakCheckResponse:
    if payload.place == "public":
        return _public(payload, min_won=min_won, prices=prices)
    return _home(payload, now.astimezone(KST), min_won=min_won)


def is_leaking(leak_won: int, min_won: int) -> bool:
    """새는 돈이 있고(0원 초과) 기준 이상일 때만. 기준이 0이어도 0원은 새지 않는다."""
    return leak_won > 0 and leak_won >= min_won


# ---------------------------------------------------------------------------
# home: 시간대
# ---------------------------------------------------------------------------


def _home(payload: CarLeakCheckRequest, now: datetime, *, min_won: int) -> CarLeakCheckResponse:
    assumptions: list[str] = []
    depart_at = payload.depart_at
    if depart_at is None:
        depart_at = default_depart_at(now)
        assumptions.append(
            f"출발 시각 미입력: {depart_at.month}월 {depart_at.day}일 오전 8시(KST) 출발로 가정"
        )

    plan_request = CarPlanRequest(
        soc_now=payload.soc_now,
        battery_capacity_wh=payload.battery_capacity_wh,
        soc_target=payload.soc_target,
        charger_kw=payload.charger_kw,
        plug_in_at=None,  # 이미 충전 중이다: 지금부터
        depart_at=depart_at,
        mode=payload.mode,
    )
    energy_kwh = _energy_kwh(payload)
    try:
        # 시각 검증(지난 출발 시각, 72시간 상한)도 여기서 같은 422로 난다.
        result = compute_car_plan(plan_request, now)
    except InsufficientTimeError:
        # 지금 바로 충전해도 출발 전에 다 못 채운다. 더 싼 선택지가 없으니 새는
        # 돈도 없다 — 422로 막는 대신 할 일(지금 계속 충전)을 말한다.
        return CarLeakCheckResponse(
            leaking=False,
            leak_won=0,
            energy_kwh=energy_kwh,
            speech="출발 전까지 목표만큼 채우려면 지금 바로 충전해야 해요.",
            assumptions=assumptions,
        )

    if not result.needs_charging:
        return _no_charge(payload, assumptions)

    plan, leak_won = result.plan, result.savings_won
    if plan is None or leak_won is None:  # needs_charging이면 car/plan이 늘 채운다
        raise RuntimeError("car/plan returned needs_charging without a plan")
    assumptions = [*result.assumptions, *assumptions]
    if not is_leaking(leak_won, min_won):
        return CarLeakCheckResponse(
            leaking=False,
            leak_won=leak_won,
            energy_kwh=plan.energy_kwh,
            speech=OK_SPEECH,
            assumptions=assumptions,
        )

    reservation = result.reservation
    start = reservation.start_at if reservation is not None else plan.start
    sentences = [
        "지금은 요금이 비싼 시간이라 돈이 새고 있어요.",
        f"{spoken_moment(start.astimezone(KST), now)}부터 충전하면 "
        f"약 {leak_won:,}원 아낄 수 있어요.",
    ]
    if reservation is not None:
        sentences.append(
            f"차량 예약 충전을 {spoken_clock(reservation.start_at.astimezone(KST))} 시작, "
            f"{spoken_clock(reservation.end_at.astimezone(KST))} 종료로 설정해 주세요."
        )
    else:
        sentences.append("충전에 24시간 넘게 걸려 차량 예약 충전 한 번으로는 설정할 수 없어요.")

    return CarLeakCheckResponse(
        leaking=True,
        leak_won=leak_won,
        cause="time",
        energy_kwh=plan.energy_kwh,
        plan=plan,
        reservation=reservation,
        speech=" ".join(sentences),
        assumptions=assumptions,
    )


# ---------------------------------------------------------------------------
# public: 결제 방식
# ---------------------------------------------------------------------------


def _public(
    payload: CarLeakCheckRequest, *, min_won: int, prices: PublicPrices
) -> CarLeakCheckResponse:
    if payload.payment is None:
        reject_field("payment", "place가 public이면 payment가 필요합니다.", None)
    if payload.charger_speed is None:
        reject_field("charger_speed", "place가 public이면 charger_speed가 필요합니다.", None)

    speed_prices = prices.for_speed(payload.charger_speed)
    unit_now = speed_prices.price(payload.payment)
    unit_member = speed_prices.price("member")
    assumptions: list[str] = list(PUBLIC_ASSUMPTIONS)
    if not speed_prices.verified:
        speed = SPEED_LABELS[payload.charger_speed]
        assumptions.append(f"{speed} 평균 단가는 소비자원 원문과 아직 대조하지 못한 값")

    if payload.soc_target <= payload.soc_now:
        response = _no_charge(payload, assumptions)
        return response.model_copy(
            update={"unit_price_now": unit_now, "unit_price_member": unit_member}
        )

    energy_kwh = _energy_kwh(payload)
    leak_won = round(energy_kwh * (unit_now - unit_member))
    leaking = is_leaking(leak_won, min_won)
    if leaking:
        label = PAYMENT_LABELS[payload.payment]
        speech = (
            f"{label}로 충전하고 있어서 돈이 새고 있어요. "
            f"이번 충전(약 {_spoken_kwh(energy_kwh)}kWh)은 회원가보다 약 {leak_won:,}원 더 나와요. "
            "이 충전소 사업자 회원으로 결제하면 아낄 수 있어요. 사업자 평균 기준 추정이에요."
        )
    else:
        speech = OK_SPEECH

    return CarLeakCheckResponse(
        leaking=leaking,
        leak_won=leak_won,
        cause="payment" if leaking else None,
        energy_kwh=energy_kwh,
        unit_price_now=unit_now,
        unit_price_member=unit_member,
        speech=speech,
        assumptions=assumptions,
    )


# ---------------------------------------------------------------------------
# 공용
# ---------------------------------------------------------------------------


def _energy_kwh(payload: CarLeakCheckRequest) -> float:
    """채울 전력량. ``planner.ChargeRequest.energy_kwh``와 같은 식(효율 1)이다."""
    gap = max(payload.soc_target - payload.soc_now, 0) / 100
    return round(payload.battery_capacity_wh / 1000 * gap, 3)


def _no_charge(payload: CarLeakCheckRequest, assumptions: list[str]) -> CarLeakCheckResponse:
    return CarLeakCheckResponse(
        leaking=False,
        leak_won=0,
        energy_kwh=0.0,
        speech=(
            f"이미 목표 잔량 {spoken_percent(payload.soc_target)}에 닿아서 "
            "더 충전하지 않아도 돼요."
        ),
        assumptions=assumptions,
    )


def _spoken_kwh(energy_kwh: float) -> str:
    """39.152 → "39", 4.25 → "4.3". 10kWh 이상은 정수, 그 밑은 소수 첫째 자리."""
    if energy_kwh >= 10:
        return f"{round(energy_kwh):,}"
    return f"{round(energy_kwh, 1):g}"
