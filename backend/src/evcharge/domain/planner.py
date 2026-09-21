from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .errors import InsufficientTimeError
from .pricing import Mode, PriceBreakdown

GRID = timedelta(minutes=15)

ASSUMPTIONS: tuple[str, ...] = (
    "충전 출력 일정",
    "연속 충전",
    "기본요금 제외, kWh당 요금만 계산",
)

PriceFn = Callable[[datetime], PriceBreakdown]


@dataclass(frozen=True)
class ChargeRequest:
    battery_kwh: float
    soc_now: float
    soc_target: float
    charger_kw: float
    earliest_start: datetime
    deadline: datetime
    mode: Mode = "self_low"
    public_base_price: float | None = None
    efficiency: float = 1.0

    @property
    def energy_kwh(self) -> float:
        gap = (self.soc_target - self.soc_now) / 100
        return self.battery_kwh * gap / self.efficiency

    @property
    def duration(self) -> timedelta:
        return timedelta(hours=self.energy_kwh / self.charger_kw)


@dataclass(frozen=True)
class ChargePlan:
    start: datetime
    end: datetime
    energy_kwh: float
    cost_won: int
    discounted_kwh: float


@dataclass(frozen=True)
class Recommendation:
    best: ChargePlan
    baseline_now: ChargePlan
    savings_won: int
    candidates_checked: int
    assumptions: list[str] = field(default_factory=lambda: list(ASSUMPTIONS))


def recommend(request: ChargeRequest, price_fn: PriceFn) -> Recommendation:
    """최저 비용 연속 충전 구간을 찾는다 (F-03, F-04).

    요금표를 모른다 — '시각 → 단가' 함수 하나만 받는다. 덕분에 요금 규칙이
    바뀌어도 탐색 로직은 그대로고, 테스트에서 가짜 단가로 검증할 수 있다.
    """
    duration = request.duration
    available = request.deadline - request.earliest_start

    if duration > available:
        raise InsufficientTimeError(
            f"시간이 부족합니다: 충전에 {duration} 필요, 가능한 시간은 {available}."
        )

    candidates = _candidate_starts(request.earliest_start, request.deadline, duration)
    plans = [_plan_for(start, request, price_fn) for start in candidates]

    # 최저 비용, 동률이면 더 이른 시작 (candidates가 이미 오름차순)
    best = min(plans, key=lambda plan: (plan.cost_won, plan.start))
    baseline = _plan_for(request.earliest_start, request, price_fn)

    return Recommendation(
        best=best,
        baseline_now=baseline,
        savings_won=baseline.cost_won - best.cost_won,
        candidates_checked=len(candidates),
        assumptions=list(ASSUMPTIONS),
    )


def _candidate_starts(
    earliest: datetime, deadline: datetime, duration: timedelta
) -> list[datetime]:
    """시작 가능 시각 자신 + 이후 15분 격자 시각들 + 가장 늦은 시작 시각.

    earliest가 격자에 맞지 않을 수 있어 본인도 후보에 넣는다 (명세 F-03).
    """
    latest = deadline - duration
    starts = {earliest, latest}

    moment = _ceil_to_grid(earliest)
    while moment <= latest:
        starts.add(moment)
        moment += GRID

    return sorted(s for s in starts if earliest <= s <= latest)


def _ceil_to_grid(moment: datetime) -> datetime:
    remainder = (moment.minute % 15, moment.second, moment.microsecond)
    if remainder == (0, 0, 0):
        return moment
    floor = moment.replace(
        minute=moment.minute - moment.minute % 15, second=0, microsecond=0
    )
    return floor + GRID


def _plan_for(start: datetime, request: ChargeRequest, price_fn: PriceFn) -> ChargePlan:
    """15분 조각으로 나눠 (조각 kWh × 조각 단가)를 합산한다."""
    duration = request.duration
    end = start + duration

    cost = 0.0
    discounted_kwh = 0.0
    moment = start

    while moment < end:
        slice_end = min(moment + GRID, end)
        slice_hours = (slice_end - moment).total_seconds() / 3600
        slice_kwh = request.charger_kw * slice_hours

        price = price_fn(moment)
        cost += slice_kwh * price.price_per_kwh
        if price.discounted:
            discounted_kwh += slice_kwh

        moment = slice_end

    return ChargePlan(
        start=start,
        end=end,
        energy_kwh=round(request.energy_kwh, 3),
        cost_won=round(cost),
        discounted_kwh=round(discounted_kwh, 3),
    )
