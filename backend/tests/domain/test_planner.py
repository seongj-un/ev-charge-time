from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from evcharge.domain.errors import InsufficientTimeError
from evcharge.domain.planner import ChargeRequest, recommend
from evcharge.domain.pricing import PriceBreakdown

KST = ZoneInfo("Asia/Seoul")


def kst(y, m, d, hour, minute=0):
    return datetime(y, m, d, hour, minute, tzinfo=KST)


def night_is_cheap(moment: datetime) -> PriceBreakdown:
    """22–08시는 60원, 나머지는 180원. 요금표와 무관하게 탐색 로직만 본다."""
    cheap = moment.hour >= 22 or moment.hour < 8
    return PriceBreakdown(
        price_per_kwh=60.0 if cheap else 180.0,
        band="light" if cheap else "peak",
        discounted=False,
    )


def flat(moment: datetime) -> PriceBreakdown:
    return PriceBreakdown(price_per_kwh=100.0, band="middle", discounted=False)


def spec_request(**overrides) -> ChargeRequest:
    """API 명세서 2-2의 예시 요청."""
    defaults = dict(
        battery_kwh=70.0,
        soc_now=30.0,
        soc_target=60.0,
        charger_kw=7.0,
        earliest_start=kst(2026, 10, 7, 18),
        deadline=kst(2026, 10, 8, 8),
    )
    return ChargeRequest(**{**defaults, **overrides})


def test_energy_needed_from_soc_gap():
    result = recommend(spec_request(), night_is_cheap)
    assert result.best.energy_kwh == pytest.approx(21.0)


def test_efficiency_increases_energy_drawn():
    result = recommend(spec_request(efficiency=0.9), night_is_cheap)
    # 도메인이 소수 3자리로 반올림한다 (float 오차가 응답에 새지 않게)
    assert result.best.energy_kwh == pytest.approx(21.0 / 0.9, abs=0.001)


def test_candidate_count_matches_the_spec_example():
    """18:00→08:00에 3시간 충전이면 15분 격자 후보가 정확히 45개."""
    result = recommend(spec_request(), night_is_cheap)
    assert result.candidates_checked == 45


def test_picks_the_cheapest_window():
    """22시부터 싸지므로 22:00 시작, 3시간 뒤 01:00 종료 — 명세 예시와 일치."""
    result = recommend(spec_request(), night_is_cheap)

    assert result.best.start == kst(2026, 10, 7, 22)
    assert result.best.end == kst(2026, 10, 8, 1)


def test_baseline_starts_immediately_and_savings_are_positive():
    result = recommend(spec_request(), night_is_cheap)

    assert result.baseline_now.start == kst(2026, 10, 7, 18)
    assert result.baseline_now.end == kst(2026, 10, 7, 21)
    assert result.savings_won > 0
    assert result.savings_won == result.baseline_now.cost_won - result.best.cost_won


def test_flat_price_prefers_the_earliest_start():
    result = recommend(spec_request(), flat)

    assert result.best.start == kst(2026, 10, 7, 18)
    assert result.savings_won == 0


def test_offgrid_earliest_start_is_kept_as_a_candidate():
    result = recommend(spec_request(earliest_start=kst(2026, 10, 7, 18, 7)), flat)

    # 18:07 자신이 최선이므로 그대로 선택된다
    assert result.best.start == kst(2026, 10, 7, 18, 7)


def test_offgrid_earliest_start_still_reaches_the_grid():
    result = recommend(
        spec_request(earliest_start=kst(2026, 10, 7, 18, 7)), night_is_cheap
    )

    # 격자 시각으로 넘어가 22:00을 찾아낸다
    assert result.best.start == kst(2026, 10, 7, 22)


def test_not_enough_time_is_rejected():
    request = spec_request(deadline=kst(2026, 10, 7, 20))

    with pytest.raises(InsufficientTimeError) as excinfo:
        recommend(request, night_is_cheap)

    message = str(excinfo.value)
    assert "3:00:00" in message
    assert "2:00:00" in message


def test_exactly_enough_time_yields_a_single_candidate():
    request = spec_request(deadline=kst(2026, 10, 7, 21))
    result = recommend(request, night_is_cheap)

    assert result.candidates_checked == 1
    assert result.best.start == kst(2026, 10, 7, 18)


def test_discounted_energy_is_reported():
    def always_discounted(moment: datetime) -> PriceBreakdown:
        return PriceBreakdown(price_per_kwh=50.0, band="middle", discounted=True)

    result = recommend(spec_request(), always_discounted)

    assert result.best.discounted_kwh == pytest.approx(result.best.energy_kwh)


def test_cost_integrates_across_a_price_change():
    """18:00 시작, 3시간 중 마지막 1시간만 싸면 비용은 두 구간의 합."""

    def cheap_after_20(moment: datetime) -> PriceBreakdown:
        cheap = moment.hour >= 20
        return PriceBreakdown(
            price_per_kwh=100.0 if cheap else 200.0,
            band="light" if cheap else "peak",
            discounted=False,
        )

    request = spec_request(deadline=kst(2026, 10, 7, 21))
    result = recommend(request, cheap_after_20)

    # 7kW로 18–20시 14kWh×200원, 20–21시 7kWh×100원 = 2800 + 700
    assert result.best.cost_won == 3500


def test_assumptions_are_reported():
    result = recommend(spec_request(), night_is_cheap)
    assert len(result.assumptions) >= 3
