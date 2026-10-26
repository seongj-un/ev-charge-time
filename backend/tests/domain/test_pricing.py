from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
import yaml

from evcharge.domain.calendar import YamlHolidayProvider
from evcharge.domain.errors import TariffNotConfiguredError
from evcharge.domain.pricing import hourly_prices, price_at
from evcharge.domain.tariff import Tariff
from evcharge.settings import get_settings

KST = ZoneInfo("Asia/Seoul")


@pytest.fixture(scope="module")
def tariff() -> Tariff:
    return Tariff.load(get_settings().tariff_path)


@pytest.fixture(scope="module")
def holidays() -> YamlHolidayProvider:
    return YamlHolidayProvider.load(get_settings().holidays_path)


def at(y, m, d, hour):
    return datetime(y, m, d, hour, tzinfo=KST)


def test_bands_are_ordered_cheapest_to_dearest(tariff, holidays):
    """경부하 < 중간부하 < 최대부하.

    절대값이 아니라 순서를 검증한다. 잠정치를 한전 공식 요금표로
    갈아끼워도 이 테스트는 그대로 살아있고 회귀를 잡는다.
    """
    weekday = date(2026, 10, 16)  # 금요일, 봄·가을
    light = price_at(at(2026, 10, 16, 2), "self_low", tariff, holidays)
    middle = price_at(at(2026, 10, 16, 9), "self_low", tariff, holidays)
    peak = price_at(at(2026, 10, 16, 16), "self_low", tariff, holidays)

    assert (light.band, middle.band, peak.band) == ("light", "middle", "peak")
    assert light.price_per_kwh < middle.price_per_kwh < peak.price_per_kwh
    assert weekday.weekday() == 4


def test_weekend_discount_lowers_price_within_same_band(tariff, holidays):
    """봄·가을 토요일 12시는 같은 날 10시와 같은 중간부하지만 더 싸다."""
    discounted = price_at(at(2026, 10, 17, 12), "self_low", tariff, holidays)
    normal = price_at(at(2026, 10, 17, 10), "self_low", tariff, holidays)

    assert discounted.band == normal.band == "middle"
    assert discounted.discounted is True
    assert normal.discounted is False
    assert discounted.price_per_kwh < normal.price_per_kwh


def test_public_fast_subtracts_flat_discount(tariff, holidays):
    saturday = price_at(
        at(2026, 10, 17, 12), "public_fast", tariff, holidays, public_base_price=350.0
    )
    sunday = price_at(
        at(2026, 10, 18, 12), "public_fast", tariff, holidays, public_base_price=350.0
    )
    weekday = price_at(
        at(2026, 10, 16, 12), "public_fast", tariff, holidays, public_base_price=350.0
    )

    assert saturday.price_per_kwh == pytest.approx(301.4)
    assert sunday.price_per_kwh == pytest.approx(307.3)
    assert weekday.price_per_kwh == pytest.approx(350.0)
    assert weekday.discounted is False


def test_public_fast_without_a_price_is_rejected(tariff, holidays):
    with pytest.raises(TariffNotConfiguredError):
        price_at(at(2026, 10, 16, 12), "public_fast", tariff, holidays)


def test_hourly_prices_covers_the_whole_day(tariff, holidays):
    hours = hourly_prices(date(2026, 10, 17), "self_low", tariff, holidays)

    assert len(hours) == 24
    assert [h.hour for h in hours] == list(range(24))
    assert [h.hour for h in hours if h.discounted] == [11, 12, 13]


def test_self_high_is_cheaper_than_self_low(tariff, holidays):
    low = price_at(at(2026, 10, 16, 16), "self_low", tariff, holidays)
    high = price_at(at(2026, 10, 16, 16), "self_high", tariff, holidays)

    assert high.price_per_kwh < low.price_per_kwh


# ── 사용자에게 보이는 오류에 개발자용 문구를 섞지 않는다 ──────────────────────
#
# 공공 급속 단가가 없을 때 나던 문구가 이랬다:
#
#   "공공 급속 단가가 없습니다. public_base_price를 보내거나
#    config/tariff.yaml의 public_fast.base_price_per_kwh를 채우세요."
#
# 이 문장은 422의 detail로 **화면에 그대로 뜬다.** 기본 차량을 공공 급속으로
# 저장해 둔 계정이 질문하기를 쓰면 바로 이 화면을 본다 — 실제로 그렇게 발견했다.
# 파일 경로와 설정 키를 사용자에게 보여 주는 것도 문제지만, 더 큰 문제는
# **읽는 사람이 고칠 수 없는 일을 시킨다**는 것이다.

_DEVELOPER_ONLY = (
    "tariff.yaml",
    "config/",
    "public_fast.",
    "base_price_per_kwh",
    "public_base_price",
)


def test_the_public_fast_error_does_not_leak_developer_instructions(tariff, holidays):
    """단가 없이 공공 급속을 계산하면 오류가 나되, 그 문구는 사용자 말이어야 한다."""
    with pytest.raises(TariffNotConfiguredError) as caught:
        price_at(datetime(2026, 10, 7, 14, tzinfo=KST), "public_fast", tariff, holidays)

    message = str(caught.value)
    for token in _DEVELOPER_ONLY:
        assert token not in message, (
            f"사용자에게 보이는 오류에 개발자용 표현 {token!r}이 들어 있다: {message!r}"
        )
    # 그러면서도 무엇을 해야 하는지는 말해야 한다.
    assert "단가" in message


# ── 자가 충전 단가는 요금표 공식 그대로여야 한다 ────────────────────────────
#
# 위 테스트들은 "어느 쪽이 더 싼가"만 본다. 그래서 할인이 없는 시간의 배수가
# 1.0이 아니어도, 연료비조정단가의 부호가 뒤집혀도 전부 통과했다(뮤테이션
# 테스트로 확인). 순서는 그대로인데 금액만 틀리는 회귀다. 기대값을 숫자로 박지
# 않고 tariff.yaml에서 다시 계산하는 이유는 위와 같다 — 요금표를 갈아끼워도
# 이 테스트는 고칠 필요가 없다.


def _expected_self_price(tariff, mode, season, band, discounted):
    energy = tariff.get(f"energy_charge.{mode}")[season][band]
    multiplier = tariff.get("weekend_discount_self")["multiplier"] if discounted else 1.0
    subtotal = (
        energy * multiplier
        + tariff.get("adders.climate_env_per_kwh")
        + tariff.get("adders.fuel_adjustment_per_kwh")
    )
    return round(subtotal * (1 + tariff.get("vat_rate") + tariff.get("power_fund_rate")), 1)


@pytest.mark.parametrize("mode", ["self_low", "self_high"])
@pytest.mark.parametrize(
    "moment,season,band,discounted",
    [
        (at(2026, 10, 16, 2), "spring_fall", "light", False),  # 금요일 새벽
        (at(2026, 10, 16, 16), "spring_fall", "peak", False),  # 금요일 오후
        (at(2026, 7, 15, 19), "summer", "peak", False),  # 여름 수요일 저녁
        (at(2026, 10, 17, 10), "spring_fall", "middle", False),  # 토요일, 할인 창 밖
        (at(2026, 10, 17, 12), "spring_fall", "middle", True),  # 토요일, 할인 창 안
        (at(2026, 10, 11, 12), "spring_fall", "light", True),  # 일요일은 종일 경부하 + 할인
        (at(2026, 10, 11, 2), "spring_fall", "light", False),  # 일요일, 할인 창 밖
        (at(2026, 12, 2, 10), "winter", "peak", False),  # 겨울 수요일 오전
        (at(2026, 12, 2, 23), "winter", "light", False),  # 겨울 수요일 밤
        (at(2026, 12, 5, 12), "winter", "middle", False),  # 겨울 토요일 — 할인 없음
    ],
)
def test_self_price_follows_the_tariff_formula(
    tariff, holidays, mode, moment, season, band, discounted
):
    """(전력량요금 × 할인배수 + 기후환경 + 연료비조정) × (1 + 부가세율 + 기금율)."""
    breakdown = price_at(moment, mode, tariff, holidays)

    assert (breakdown.band, breakdown.discounted) == (band, discounted)
    assert breakdown.price_per_kwh == pytest.approx(
        _expected_self_price(tariff, mode, season, band, discounted)
    )


def test_weekend_discount_halves_only_the_energy_charge(tariff, holidays):
    """할인은 전력량요금에만 걸린다. 가산 항목(기후환경·연료비조정)까지 깎으면
    할인 폭이 실제보다 커진다. 같은 날 같은 부하구간의 두 시각을 비교하면
    차이는 정확히 '전력량요금 × (1 − 배수) × (1 + 세금·기금)'이다."""
    normal = price_at(at(2026, 10, 17, 10), "self_low", tariff, holidays)
    discounted = price_at(at(2026, 10, 17, 12), "self_low", tariff, holidays)

    energy = tariff.get("energy_charge.self_low")["spring_fall"]["middle"]
    multiplier = tariff.get("weekend_discount_self")["multiplier"]
    taxes = 1 + tariff.get("vat_rate") + tariff.get("power_fund_rate")

    assert normal.price_per_kwh - discounted.price_per_kwh == pytest.approx(
        energy * (1 - multiplier) * taxes, abs=0.1
    )


# ── 공식과 독립적인 손계산 기대값 ─────────────────────────────────────────────
#
# 위 공식 테스트는 기대값을 구현과 같은 식으로 만든다. 그래서 구현이 바뀌는 회귀는
# 잡지만 식 자체가 처음부터 틀렸다면 같이 통과한다. 여기서는 숫자를 고른 가짜
# 요금표로 손계산한 값과 비교한다. 연료비조정단가는 음수(실제로 분기마다
# −5~+5원 사이에서 바뀐다)로 둬서 부호를 버리는 실수(abs 등)도 드러나게 한다.


@pytest.fixture(scope="module")
def round_number_tariff(tmp_path_factory) -> Tariff:
    raw = yaml.safe_load(get_settings().tariff_path.read_text(encoding="utf-8"))
    raw["energy_charge"]["self_low"]["value"]["spring_fall"] = {
        "light": 80.0,
        "middle": 100.0,
        "peak": 120.0,
    }
    raw["adders"]["climate_env_per_kwh"]["value"] = 9.3
    raw["adders"]["fuel_adjustment_per_kwh"]["value"] = -5.0
    raw["vat_rate"]["value"] = 0.1
    raw["power_fund_rate"]["value"] = 0.0

    path = tmp_path_factory.mktemp("tariff") / "tariff.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return Tariff.load(path)


@pytest.mark.parametrize(
    "moment,expected",
    [
        (at(2026, 10, 17, 10), 114.7),  # (100 + 9.3 − 5) × 1.1 = 114.73
        (at(2026, 10, 17, 12), 59.7),  # (100 × 0.5 + 9.3 − 5) × 1.1 = 59.73
        (at(2026, 10, 11, 12), 48.7),  # (80 × 0.5 + 9.3 − 5) × 1.1 = 48.73
    ],
)
def test_self_price_matches_hand_calculation(round_number_tariff, holidays, moment, expected):
    breakdown = price_at(moment, "self_low", round_number_tariff, holidays)

    assert breakdown.price_per_kwh == expected
