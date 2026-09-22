from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from evcharge.domain.calendar import (
    YamlHolidayProvider,
    band_at,
    day_type_of,
    is_discount_hour,
    season_of,
)
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


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 5, 31), "spring_fall"),
        (date(2026, 6, 1), "summer"),
        (date(2026, 8, 31), "summer"),
        (date(2026, 9, 1), "spring_fall"),
        (date(2026, 10, 31), "spring_fall"),
        (date(2026, 11, 1), "winter"),
        (date(2027, 2, 28), "winter"),
        (date(2027, 3, 1), "spring_fall"),
    ],
)
def test_season_boundaries(tariff, day, expected):
    assert season_of(day, tariff) == expected


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 10, 7), "weekday"),        # 수요일
        (date(2026, 10, 10), "saturday"),      # 토요일
        (date(2026, 10, 11), "sunday_holiday"),  # 일요일
        (date(2026, 10, 3), "sunday_holiday"),   # 개천절 — 토요일이지만 공휴일 우선
    ],
)
def test_day_type(holidays, day, expected):
    assert day_type_of(day, holidays) == expected


def test_sunday_is_light_all_day(tariff, holidays):
    for hour in range(24):
        assert band_at(at(2026, 10, 11, hour), tariff, holidays) == "light"


def test_saturday_demotes_peak_to_middle(tariff, holidays):
    # 2026-10-16(금)과 2026-10-17(토)은 같은 계절, 같은 시각, 둘 다 공휴일 아님
    assert band_at(at(2026, 10, 16, 16), tariff, holidays) == "peak"
    assert band_at(at(2026, 10, 17, 16), tariff, holidays) == "middle"


def test_saturday_keeps_light_and_middle(tariff, holidays):
    assert band_at(at(2026, 10, 17, 2), tariff, holidays) == "light"
    assert band_at(at(2026, 10, 17, 9), tariff, holidays) == "middle"


def test_winter_weekday_bands(tariff, holidays):
    # 2026-12-02는 수요일
    assert band_at(at(2026, 12, 2, 10), tariff, holidays) == "peak"
    assert band_at(at(2026, 12, 2, 13), tariff, holidays) == "middle"
    assert band_at(at(2026, 12, 2, 17), tariff, holidays) == "peak"
    assert band_at(at(2026, 12, 2, 23), tariff, holidays) == "light"


@pytest.mark.parametrize(
    "moment,expected",
    [
        (at(2026, 10, 10, 11), True),   # 봄가을 토요일 11시
        (at(2026, 10, 10, 13), True),   # 13시 (14시 미만)
        (at(2026, 10, 10, 14), False),  # 14시는 제외
        (at(2026, 10, 10, 10), False),  # 11시 이전
        (at(2026, 10, 11, 12), True),   # 봄가을 일요일
        (at(2026, 7, 11, 12), False),   # 여름 토요일 — 할인 없음
        (at(2026, 10, 7, 12), False),   # 봄가을 평일 — 할인 없음
    ],
)
def test_discount_hours(tariff, holidays, moment, expected):
    assert is_discount_hour(moment, tariff, holidays) is expected


def test_holiday_on_saturday_beats_weekday_table(tariff, holidays):
    """2026-10-09 한글날은 금요일이지만 공휴일이라 종일 경부하."""
    assert band_at(at(2026, 10, 9, 16), tariff, holidays) == "light"


# ── 실제 설정의 시간대 표를 1차 자료에 고정한다 ─────────────────────────────
#
# 이 테스트가 없어서 시간대 표가 통째로 틀린 채 오래 살아남았다. 부하구간의
# 대소 관계만 검증하는 불변식 테스트는 요금표가 바뀌어도 살아남는다는 장점이
# 있지만, 바로 그 이유로 **표 자체가 틀린 것은 잡지 못한다.**
#
# 그래서 여기서만 24시간을 절대값으로 못 박는다. 근거는 기후에너지환경부
# 보도자료 2026-04-14 「낮엔 낮추고 저녁은 높인다」 붙임 3 「3. 계절·시간대별
# 구분」(산업용(을)·EV 충전전력 기준, 2026-04-16 시행)이며, 원문 PDF가
# config/20260414(mcee-tou).pdf 에 있다.
#
#   여름철·봄·가을철 (붙임 3에서 두 계절이 병합된 한 칸이다)
#     경부하   22:00~08:00
#     중간부하 08:00~15:00, 21:00~22:00
#     최대부하 15:00~21:00
#
#   겨울철 (개편 전후 동일)
#     경부하   22:00~08:00
#     중간부하 08:00~09:00, 12:00~16:00, 19:00~22:00
#     최대부하 09:00~12:00, 16:00~19:00
#
# 표가 또 바뀌면 이 테스트가 깨진다. 그때 고쳐야 하는 것은 기대값이 아니라
# 위 출처다 — 새 1차 자료를 확보한 뒤에 함께 고친다.

L, M, P = "light", "middle", "peak"

_SUMMER_AND_SPRING_FALL = (
    [L] * 8  # 00–08
    + [M] * 7  # 08–15
    + [P] * 6  # 15–21
    + [M]  # 21–22
    + [L] * 2  # 22–24
)
_WINTER = (
    [L] * 8  # 00–08
    + [M]  # 08–09
    + [P] * 3  # 09–12
    + [M] * 4  # 12–16
    + [P] * 3  # 16–19
    + [M] * 3  # 19–22
    + [L] * 2  # 22–24
)


@pytest.mark.parametrize(
    ("label", "y", "m", "d", "expected"),
    [
        # 셋 다 평일이어야 한다 — 토요일·공휴일 규칙이 끼어들면 표를 보는 게 아니다.
        ("여름 (2026-07-15 수)", 2026, 7, 15, _SUMMER_AND_SPRING_FALL),
        ("봄·가을 (2026-10-07 수)", 2026, 10, 7, _SUMMER_AND_SPRING_FALL),
        ("겨울 (2026-11-11 수)", 2026, 11, 11, _WINTER),
    ],
)
def test_real_config_matches_the_official_time_band_table(
    label, y, m, d, expected, tariff, holidays
):
    assert date(y, m, d).weekday() < 5, f"{label}: 평일이어야 한다"
    actual = [band_at(at(y, m, d, h), tariff, holidays) for h in range(24)]
    assert actual == expected, f"{label} 시간대 표가 붙임 3과 다르다"


def test_evening_18_to_21_is_peak_outside_winter(tariff, holidays):
    """2026-04-16 개편의 핵심이자 이 서비스의 대표 시나리오가 걸린 구간.

    퇴근 후 18시에 꽂는 것이 가장 비싸졌다는 사실이 추천의 근거다.
    개편 전에는 이 구간이 중간부하였다.
    """
    for hour in (18, 19, 20):
        assert band_at(at(2026, 10, 7, hour), tariff, holidays) == "peak"
        assert band_at(at(2026, 7, 15, hour), tariff, holidays) == "peak"
    # 21시부터는 중간부하로 내려온다 — 경계가 21:00인지 22:00인지가 관건이었다.
    assert band_at(at(2026, 10, 7, 21), tariff, holidays) == "middle"


def test_midday_11_to_15_is_no_longer_peak_outside_winter(tariff, holidays):
    """개편으로 낮이 내려왔다 — 태양광이 많은 시간으로 수요를 옮기려는 취지다."""
    for hour in range(11, 15):
        assert band_at(at(2026, 10, 7, hour), tariff, holidays) == "middle"
        assert band_at(at(2026, 7, 15, hour), tariff, holidays) == "middle"
    # 15시부터 최대부하가 시작된다.
    assert band_at(at(2026, 10, 7, 15), tariff, holidays) == "peak"
