"""물리 기반 일사량 근사 (F-09).

**불변식으로 검증한다.** 요금 테스트를 잠정치와 무관하게 짠 것과 같은 이유다 —
감쇠 계수나 맑은날 공식의 상수는 더 나은 근거가 나오면 바뀔 값이고, 그때
"해가 지면 0", "흐리면 맑을 때보다 작다" 같은 성질까지 같이 깨져서는 안 된다.
절대값을 박아두면 상수를 고칠 때마다 테스트가 같이 고쳐져 회귀를 못 잡는다.

절대값을 보는 곳은 한 군데(``test_clear_sky_noon_is_physically_plausible``)뿐이고,
그것도 "지표 최대 일사량은 대략 1000 W/m² 언저리"라는 물리적 상한선을 넘지
않는지 보는 넓은 범위 검사다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from evcharge.domain.errors import DomainError
from evcharge.domain.pricing import KST
from evcharge.domain.solar import (
    SKY_OCTAS,
    UnknownSkyCodeError,
    clear_sky_ghi_wm2,
    cloud_transmittance,
    ghi_wm2,
    solar_elevation_deg,
)

# 빛가람(나주) — 대회 지역
NAJU_LAT, NAJU_LNG = 35.0160, 126.7108

SUMMER = datetime(2026, 6, 21, tzinfo=KST)  # 하지
WINTER = datetime(2026, 12, 21, tzinfo=KST)  # 동지


def at(base: datetime, hour: int) -> datetime:
    return base.replace(hour=hour, minute=30)


def clear(base: datetime, hour: int) -> float:
    return clear_sky_ghi_wm2(NAJU_LAT, NAJU_LNG, at(base, hour))


# ── 불변식 1: 해가 지면 0 ────────────────────────────────────────────────


@pytest.mark.parametrize("hour", [0, 1, 2, 3, 22, 23])
def test_night_hours_produce_no_irradiance(hour):
    """한밤중에는 맑든 흐리든 발전량이 0이다."""
    assert clear(SUMMER, hour) == 0.0
    assert ghi_wm2(NAJU_LAT, NAJU_LNG, at(SUMMER, hour), sky="1", pty="0") == 0.0


def test_sun_is_below_the_horizon_at_night_and_above_at_noon():
    assert solar_elevation_deg(NAJU_LAT, NAJU_LNG, at(SUMMER, 2)) < 0
    assert solar_elevation_deg(NAJU_LAT, NAJU_LNG, at(SUMMER, 12)) > 0


def test_winter_nights_are_longer_than_summer_nights():
    """겨울 06시는 아직 해가 안 떴고, 여름 06시는 떴다 — 계절이 반영된다."""
    assert clear(WINTER, 6) == 0.0
    assert clear(SUMMER, 6) > 0.0


# ── 불변식 2: 흐리면 맑을 때보다 작다 ────────────────────────────────────


def test_cloudier_sky_never_produces_more_than_a_clearer_sky():
    """SKY 코드가 흐려질수록 일사량이 단조 감소한다.

    실측으로 확인한 SKY 코드 순서(1 < 3 < 4, 값이 클수록 흐림)를 그대로
    반영해야 한다. 이 순서가 뒤집히면 "맑은 날 오후에 충전하라"는 추천이
    거꾸로 나온다.
    """
    noon = at(SUMMER, 12)
    values = [ghi_wm2(NAJU_LAT, NAJU_LNG, noon, sky=s, pty="0") for s in ("1", "3", "4")]

    assert values[0] > values[1] > values[2] > 0


def test_precipitation_attenuates_at_least_as_much_as_overcast():
    """비가 오는데 흐린 날보다 밝을 수는 없다."""
    noon = at(SUMMER, 12)
    overcast = ghi_wm2(NAJU_LAT, NAJU_LNG, noon, sky="4", pty="0")

    for pty in ("1", "2", "3", "4"):
        raining = ghi_wm2(NAJU_LAT, NAJU_LNG, noon, sky="4", pty=pty)
        assert raining <= overcast
        assert raining > 0  # 비가 와도 낮은 밤보다 밝다


def test_precipitation_overrides_a_clear_sky_code():
    """PTY가 강수를 가리키면 SKY가 '맑음'이어도 강수 기준으로 깎는다.

    강수형태는 '비가 내리고 있다'는 뜻이므로 하늘은 정의상 덮여 있다.
    두 값이 어긋나면 강수 쪽을 믿는다.
    """
    noon = at(SUMMER, 12)
    clear_dry = ghi_wm2(NAJU_LAT, NAJU_LNG, noon, sky="1", pty="0")
    clear_wet = ghi_wm2(NAJU_LAT, NAJU_LNG, noon, sky="1", pty="1")

    assert clear_wet < clear_dry


def test_transmittance_stays_within_physical_bounds():
    for sky in SKY_OCTAS:
        for pty in ("0", "1", "4"):
            factor = cloud_transmittance(sky, pty)
            assert 0.0 < factor <= 1.0


# ── 불변식 3: 여름 정오 > 겨울 정오 ─────────────────────────────────────


def test_summer_noon_beats_winter_noon():
    """태양 고도각이 높은 만큼 여름 정오가 더 세다.

    지구-태양 거리는 1월에 가장 가까워(근일점) 대기권 밖 일사량은 겨울이
    오히려 3% 높다. 그걸 고려해도 고도각 차이가 압도적이라는 것까지 본다.
    """
    assert clear(SUMMER, 12) > clear(WINTER, 12) * 1.5


def test_noon_is_the_daily_maximum():
    """하루 중 최대는 남중 시각 근처(한국은 KST 12~13시)다."""
    day = [clear(SUMMER, h) for h in range(24)]
    peak_hour = max(range(24), key=lambda h: day[h])

    assert peak_hour in (12, 13)


def test_irradiance_rises_to_noon_and_falls_after():
    """오전에는 단조 증가, 오후에는 단조 감소한다."""
    morning = [clear(SUMMER, h) for h in range(6, 12)]
    afternoon = [clear(SUMMER, h) for h in range(13, 19)]

    assert morning == sorted(morning)
    assert afternoon == sorted(afternoon, reverse=True)


# ── 넓은 범위의 물리적 타당성 ───────────────────────────────────────────


def test_clear_sky_noon_is_physically_plausible():
    """맑은 날 정오 지표 일사량은 대략 1000 W/m²를 넘지 않는다.

    표준시험조건(STC)의 기준 일사량이 1000 W/m²이고, 지표에서 그보다 크게
    넘는 값은 모델이 틀렸다는 뜻이다. 하한(500)은 "정오인데 흐린 날만큼
    어둡다"는 명백한 오류를 잡는다.
    """
    assert 500.0 < clear(SUMMER, 12) < 1050.0
    assert 250.0 < clear(WINTER, 12) < 700.0


def test_higher_latitude_gets_less_sun_at_winter_noon():
    """같은 시각이면 북쪽이 더 약하다 (위도가 실제로 쓰인다)."""
    seoul = clear_sky_ghi_wm2(37.5665, 126.9780, at(WINTER, 12))
    jeju = clear_sky_ghi_wm2(33.4996, 126.5312, at(WINTER, 12))

    assert jeju > seoul


def test_solar_noon_lags_clock_noon_in_korea():
    """한국 표준시(UTC+9)의 기준 경도는 135°E인데 나주는 126.7°E다.

    그래서 남중은 시계상 12시가 아니라 12시 30분쯤이다. 경도 보정과
    균시차를 빼먹으면 이 차이가 사라진다.
    """
    elevations = {
        minute: solar_elevation_deg(
            NAJU_LAT, NAJU_LNG, datetime(2026, 6, 21, 12, minute, tzinfo=KST)
        )
        for minute in range(0, 60, 5)
    }
    peak_minute = max(elevations, key=lambda m: elevations[m])

    assert peak_minute >= 20


# ── 모르는 코드는 지어내지 않는다 ───────────────────────────────────────


def test_unknown_sky_code_raises_instead_of_guessing():
    """관측하지 못한 SKY 코드에 임의의 감쇠를 매기지 않는다.

    이 저장소는 충전소 ``stat`` 코드에서 문서에 없는 값이 11.9%나 나오는
    일을 이미 겪었다. 모르는 값에 그럴듯한 숫자를 붙이면 틀린 줄도 모르고
    쓰게 되므로, 크게 터뜨리고 호출자가 그 시간대를 빼도록 한다.
    """
    with pytest.raises(UnknownSkyCodeError):
        cloud_transmittance("2", "0")

    with pytest.raises(UnknownSkyCodeError):
        cloud_transmittance("", "0")


def test_unknown_sky_code_error_is_a_domain_error():
    """api/errors.py가 422로 옮길 수 있도록 도메인 예외 계열이어야 한다."""
    assert issubclass(UnknownSkyCodeError, DomainError)


def test_unknown_precipitation_code_is_treated_as_precipitating():
    """모르는 PTY 값은 '강수 중'으로 본다.

    PTY는 '강수의 형태'라서 0이 아닌 값은 형태가 무엇이든 비가 오거나 눈이
    온다는 뜻이다 — 코드표를 몰라도 하늘이 덮여 있다는 것은 정의로 안다.
    SKY와 달리 안전한 기본값이 존재하므로 터뜨리지 않는다.
    """
    noon = at(SUMMER, 12)
    known = ghi_wm2(NAJU_LAT, NAJU_LNG, noon, sky="4", pty="1")
    unknown = ghi_wm2(NAJU_LAT, NAJU_LNG, noon, sky="4", pty="9")

    assert unknown == known
