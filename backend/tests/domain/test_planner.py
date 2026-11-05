from datetime import datetime
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
    defaults = {
        "battery_kwh": 70.0,
        "soc_now": 30.0,
        "soc_target": 60.0,
        "charger_kw": 7.0,
        "earliest_start": kst(2026, 10, 7, 18),
        "deadline": kst(2026, 10, 8, 8),
    }
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
    assert message.startswith("시간이 부족해요.")
    assert "충전에 약 3시간이 걸리는데 가능한 시간은 2시간이에요" in message
    assert ":00" not in message  # timedelta 표기가 새지 않는다


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        (8, "8시간"),
        (4.5, "4시간 30분"),
        (0.25, "15분"),
        (0.001, "1분"),
        (42.857142, "1일 18시간 51분"),
        (48, "2일"),
        (1e20, "100,000,000,000,000,000,000시간"),
    ],
)
def test_span_is_written_for_people(hours, expected):
    from evcharge.domain.planner import format_span_hours

    assert format_span_hours(hours) == expected


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


# ── 요금이 바뀌는 시각에서도 조각을 나눈다 ─────────────────────────────────────
#
# 예전에는 시작 시각부터 15분씩 잘라 조각 첫 순간의 단가를 조각 전체에 썼다.
# 07:59에 시작하면 07:59–08:14가 통째로 경부하 단가가 되어, 08시에 이미 비싸진
# 14분이 싸게 계산됐다. 탐색은 이 착시를 "최저가"로 골라냈다 — 후보에는 격자에서
# 어긋난 시작 시각(earliest_start 자신, 가장 늦은 시작)이 들어가기 때문이다.


def test_a_slice_does_not_carry_the_old_price_across_a_price_change():
    """07:59 시작 15분(1 kWh/분 × 15분 = 0.25h × 60kW = 15 kWh).

    1분은 60원, 14분은 180원이어야 한다: 1 × 60 + 14 × 180 = 2,580원.
    """
    request = ChargeRequest(
        battery_kwh=100.0,
        soc_now=0.0,
        soc_target=15.0,
        charger_kw=60.0,
        earliest_start=kst(2026, 7, 1, 7, 59),
        deadline=kst(2026, 7, 1, 8, 14),
    )

    result = recommend(request, night_is_cheap)

    assert result.best.start == kst(2026, 7, 1, 7, 59)
    assert result.best.cost_won == 1 * 60 + 14 * 180


def test_a_misaligned_start_is_not_mistaken_for_the_cheapest():
    """07:59와 22:00 중 고를 수 있으면 실제로 싼 22:00을 골라야 한다.

    예전 계산으로는 07:59 시작 15분이 22:00 시작과 똑같이 "전부 60원"이라
    동률이었고, 동률이면 더 이른 시작을 고르므로 비싼 07:59를 추천했다.
    """
    request = ChargeRequest(
        battery_kwh=100.0,
        soc_now=0.0,
        soc_target=15.0,
        charger_kw=60.0,
        earliest_start=kst(2026, 7, 1, 7, 59),
        deadline=kst(2026, 7, 1, 22, 15),
    )

    result = recommend(request, night_is_cheap)

    assert result.best.start == kst(2026, 7, 1, 22)
    assert result.best.cost_won == 15 * 60


@pytest.mark.parametrize("charger_kw", [1e-300, 1e-12])
def test_an_astronomical_charge_time_is_insufficient_time_not_an_overflow(charger_kw):
    """도메인은 스키마를 거치지 않고도 불릴 수 있다. timedelta 범위를 넘는 충전
    시간은 OverflowError가 아니라 '시간이 부족하다'여야 한다."""
    with pytest.raises(InsufficientTimeError):
        recommend(spec_request(charger_kw=charger_kw), night_is_cheap)
