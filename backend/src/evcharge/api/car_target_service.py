"""목표 충전량 추천 (BE-11, POST /api/car/charge-target).

앱은 차의 충전 한도를 직접 바꾸지 않는다(Vehicle SDK setEvChargePercentLimit은 App Market
제어 권한이 필요하다). 서버는 "몇 %까지 채우면 되는지"만 계산해 말해 주고, 운전자가 차 설정에
넣거나 충전 계획(BE-1)의 ``soc_target``으로 쓴다.

계산
- 기본은 ``CAR_TARGET_DAILY``(80%). 배터리 보호를 위해 매일 100%까지 채우지 않는다.
- 다음 이동 거리와 전비가 다 있으면 필요 잔량 = 거리 / (전비 x 용량 kWh) x 100. 여기에 도착
  여유 ``CAR_TARGET_RESERVE``(20%p)를 더해 5% 단위로 올림하고, 평소 목표~100으로 자른다.
- 필요 잔량 + 여유가 100을 넘으면 목표 100에 ``needs_charge_on_route``.

나눗셈은 분수(Fraction)로 한다. 부동소수 오차로 정확히 5의 배수인 값(95.000...01)이 한 칸
위(100)로 올라가지 않게 하려는 것이다.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Literal

from ..settings import get_settings
from .car_plan_service import spoken_percent
from .schemas import CarChargeTargetRequest, CarChargeTargetResponse

STEP = 5

SocWhen = Literal["now", "arrival"]


def _exact(value: float) -> Fraction:
    """요청에 적힌 십진 값 그대로(``5.1`` → 51/10). float의 이진 오차를 들이지 않는다."""
    return Fraction(repr(value))


def needed_soc(next_trip_km: float, efficiency_km_per_kwh: float, capacity_wh: float) -> Fraction:
    """다음 이동에 드는 잔량(%). 100을 넘을 수 있다."""
    capacity_kwh = _exact(capacity_wh) / 1000
    return _exact(next_trip_km) * 100 / (_exact(efficiency_km_per_kwh) * capacity_kwh)


def spoken_km(km: float) -> str:
    """230 → "230킬로미터", 230.47 → "230.5킬로미터"(소수 첫째 자리)."""
    return f"{round(km, 1):g}킬로미터"


def compute_charge_target(
    payload: CarChargeTargetRequest, *, soc_when: SocWhen = "now"
) -> CarChargeTargetResponse:
    """``soc_when``: ``soc_now``가 언제의 잔량인지. HTTP API는 지금(충전을 시작할 때나 주차
    뒤), 음성은 내비 도착 예상 잔량을 넘길 때 "arrival"이다. 문장의 시점이 그에 맞춰진다.
    """
    settings = get_settings()
    daily = settings.car_target_daily
    reserve = settings.car_target_reserve
    assumptions: list[str] = []

    if payload.next_trip_km is None or payload.efficiency_km_per_kwh is None:
        missing = [
            name
            for name, value in (
                ("다음 이동 거리", payload.next_trip_km),
                ("전비", payload.efficiency_km_per_kwh),
            )
            if value is None
        ]
        assumptions.append(f"{'와 '.join(missing)}를 몰라 평소 기준 {daily}%로 정했어요.")
        return _response(daily, "unknown", None, payload, assumptions, soc_when)

    need = needed_soc(
        payload.next_trip_km, payload.efficiency_km_per_kwh, payload.battery_capacity_wh
    )
    want = need + reserve
    assumptions.append(
        f"충전 후 평균 전비 {payload.efficiency_km_per_kwh:g}km/kWh와 배터리 용량 "
        f"{payload.battery_capacity_wh / 1000:g}kWh로 계산했어요. 도착 여유 {reserve}%p를 "
        "더했어요."
    )
    # 필요 잔량이 100이면 도착 추정이 0%다. 경로 위 충전소(runs_out: 추정 0 이하)와 같은
    # 기준으로 "모자라다"로 본다. 여유가 0으로 설정돼도 같다.
    if want > 100 or need >= 100:
        return _response(100, "insufficient", need, payload, assumptions, soc_when)
    target = max(daily, math.ceil(want / STEP) * STEP)
    if target <= daily:
        return _response(daily, "daily", need, payload, assumptions, soc_when)
    return _response(min(target, 100), "long_trip", need, payload, assumptions, soc_when)


def _response(
    target: int,
    reason: str,
    need: Fraction | None,
    payload: CarChargeTargetRequest,
    assumptions: list[str],
    soc_when: SocWhen,
) -> CarChargeTargetResponse:
    # 끝에 붙는 질문(거리를 말해 달라). 잔량 문장 뒤에 둬서 운전자가 바로 답하게 한다.
    ask = ""
    if reason == "unknown":
        # 계산하지 않았으니 "충분해요"라고 단정하지 않는다. 장거리일 수도 있다.
        if payload.next_trip_km is None:
            speech = f"다음 이동 거리를 몰라서 평소처럼 {target}%를 권해요."
            ask = " 멀리 가시면 거리를 말씀해 주세요."
        else:
            speech = f"전비를 몰라서 평소처럼 {target}%를 권해요."
    elif reason == "daily":
        # 필요 잔량 + 여유가 평소 목표 이하로 계산된 경우만
        speech = f"평소처럼 {target}%까지만 채우면 충분해요."
    elif reason == "long_trip":
        speech = f"{spoken_km(payload.next_trip_km)}를 가시려면 {target}%까지 채우세요."
    elif need is not None and need >= 100:
        # 여유가 아니라 이동 자체가 모자라다. "여유가 부족해요"는 닿는다고 들린다.
        speech = "100%로 채워도 도착하기 전에 배터리가 모자라요. 가는 길에 급속충전을 하세요."
    else:
        speech = "100%로 채워도 도착할 때 여유가 부족해요. 가는 길에 급속충전을 한 번 하세요."
    if payload.soc_now is not None and payload.soc_now >= target:
        when = "도착하면" if soc_when == "arrival" else "지금"
        speech += f" {when} {spoken_percent(payload.soc_now)}라 더 채우지 않아도 돼요."
    speech += ask
    return CarChargeTargetResponse(
        soc_target=target,
        reason=reason,
        needed_soc=None if need is None else round(float(need), 1),
        needs_charge_on_route=reason == "insufficient",
        speech=speech,
        assumptions=assumptions,
    )
