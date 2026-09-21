"""물리 기반 일사량 근사 (F-09).

학습 데이터로 회귀모델을 만드는 대신 **맑은날 일사량을 기상 예보로 감쇠시키는
물리 근사**를 쓴다. 학습 데이터 수집·정제 없이 돌아가고, 계산식을 심사에서
그대로 설명할 수 있다.

계산은 두 단계다::

    맑은날 수평면 일사량(W/m²)  ×  구름·강수 투과율  =  예측 일사량(W/m²)

**이 모듈이 내놓는 것은 단위면적당 일사량(W/m²)이지 발전량(MWh)이 아니다.**
MWh로 바꾸려면 그 지역의 태양광 설비용량이 필요한데 이 프로젝트에는 없다
(``api/solar_service.py`` 참고).

근거가 되는 공식과 상수는 모두 출처를 달았다. 지어낸 숫자는 없다.

## 1. 태양 위치 — Spencer (1971)

적위·균시차·지구-태양 거리 보정을 한 논문의 푸리에 급수로 통일했다
(J.W. Spencer, "Fourier series representation of the position of the Sun",
Search 2(5), 1971). Cooper(1969)의 간단식보다 정확하고, 세 값의 출처가
하나로 묶인다.

경도 보정과 균시차를 반드시 넣는다: 한국 표준시의 기준 자오선은 135°E인데
나주는 126.7°E라, 남중이 시계상 12시가 아니라 **12시 30분쯤**이다. 이걸
빼먹으면 예측 곡선이 30분 일찍 뜬다.

## 2. 대기질량 — Kasten & Young (1989)

``AM = 1 / (sin α + 0.50572·(α + 6.07995)^-1.6364)`` (α는 도 단위 고도각).
단순한 ``1/sin α``와 달리 해가 지평선에 가까울 때 발산하지 않는다
(F. Kasten, A.T. Young, Applied Optics 28(22), 1989).

## 3. 맑은날 일사량 — Meinel & Meinel (1976)

``DNI = I₀·0.7^(AM^0.678)``, ``GHI = DNI·sin α·1.1``. 1.1배는 산란(확산)
일사를 근사로 더하는 항이다 (A.B. Meinel, M.P. Meinel, *Applied Solar
Energy*, 1976). 태양상수는 1361 W/m² (Kopp & Lean, 2011).

## 4. 구름 감쇠 — Kasten & Czeplak (1980)

``GHI / GHI_clear = 1 − 0.75·(N/8)^3.4`` — N은 옥타(0~8) 단위 전운량.
함부르크 10년 관측에서 얻은 널리 쓰이는 경험식이다 (F. Kasten, G. Czeplak,
Solar Energy 24(2), 1980).

**감쇠 계수를 따로 지어내지 않고 이 식 하나로 통일한 이유**: SKY 코드마다
"맑으면 0.9, 흐리면 0.4" 같은 숫자를 임의로 박으면 근거가 없다. 대신 SKY
코드를 전운량(옥타)으로 옮기고 — 그 대응은 기상청이 공개한 하늘상태 정의
(전운량 0~10 기준: 맑음 0~5, 구름많음 6~8, 흐림 9~10)의 **구간 중앙값**을
쓴다 — 나머지는 위 식이 정한다. 고칠 곳은 ``SKY_OCTAS`` 한 군데다.
"""

from __future__ import annotations

from datetime import datetime
from math import asin, cos, degrees, pi, radians, sin

from .errors import DomainError

# ── 모델 버전 ────────────────────────────────────────────────────────────
# 물리 모델이므로 "계산식의 버전"이다. 규칙:
#   major — 식의 구조가 바뀔 때 (예: 경사면 일사 모델 추가, 맑은날 모델 교체)
#   minor — 식은 그대로고 상수만 바뀔 때 (감쇠 계수, SKY→옥타 대응, 태양상수)
# 응답에 실어 보내므로, 저장된 예측이 어느 식으로 나온 값인지 나중에 구분된다.
MODEL_VERSION = "solar-physical-1.0"

# ── 물리 상수 ────────────────────────────────────────────────────────────
SOLAR_CONSTANT_WM2 = 1361.0  # 태양상수 (Kopp & Lean 2011)
ATMOSPHERIC_TRANSMITTANCE = 0.7  # Meinel 맑은날 대기 투과율
DIFFUSE_FACTOR = 1.1  # 산란 일사 보정 (Meinel)
# 표준시험조건(STC) 기준 일사량. 0~1 지수로 정규화할 때의 분모다
# (IEC 61215 / ASTM G-173). "지수 1.0 = 패널 정격 조건"이라는 뜻이 된다.
STC_IRRADIANCE_WM2 = 1000.0

# Kasten & Czeplak (1980)
CLOUD_ATTENUATION_A = 0.75
CLOUD_ATTENUATION_B = 3.4
MAX_OCTAS = 8.0

# ── 기상청 코드 대응 (한 곳에만 둔다) ────────────────────────────────────
#
# SKY(하늘상태) → 전운량(옥타). 실측으로 확인한 것과 그 근거:
#
#   * 2026-09-21에 전국 26개 격자 × 여러 발표시각에서 4,488개 시간대를 표본
#     조사했을 때 **관측된 SKY 값은 1·3·4뿐**이었다. 2는 한 번도 나오지 않았다.
#   * 강수확률(POP) 평균이 SKY와 함께 단조 증가했다:
#       SKY=1 → 0.1%,  SKY=3 → 19.9%,  SKY=4 → 38.6%
#     즉 **값이 클수록 흐리다**는 순서가 관측으로 확인된다.
#   * 강수(PTY≠0)인 시간대는 247건 전부 SKY=4였다.
#
# 옥타 값은 기상청 하늘상태 정의(전운량 0~10: 맑음 0~5, 구름많음 6~8,
# 흐림 9~10)의 구간 중앙값 2.5·7.0·9.5를 옥타(0~8)로 환산(×0.8)한 것이다.
#
# 이 대응이 틀렸다고 밝혀지면 **여기만** 고치면 된다. 코드 2가 다시 쓰이기
# 시작하면 아래 ``cloud_transmittance``가 예외를 던지므로 조용히 틀리지 않는다.
SKY_OCTAS: dict[str, float] = {
    "1": 2.0,  # 맑음   (전운량 0~5 의 중앙값 2.5 → 2.0 옥타)
    "3": 5.6,  # 구름많음 (6~8 의 중앙값 7.0 → 5.6 옥타)
    "4": 7.6,  # 흐림   (9~10 의 중앙값 9.5 → 7.6 옥타)
}

# PTY(강수형태)가 0이 아니면 형태와 무관하게 전운량을 최대로 본다.
#
# 이건 코드표 추측이 아니라 **정의에서 따라오는 결론**이다: PTY는 "강수의
# 형태"라서 0이 아닌 값은 비든 눈이든 소나기든 강수가 내리고 있다는 뜻이고,
# 강수 중인 하늘은 덮여 있다. 그래서 문서에 없는 값이 새로 나와도 안전하다.
#
# 실측(2026-09-21, 과거 발표분 포함)에서 관측한 PTY 값은 0·1·4뿐이었다:
#   PTY=1 — n=247, 평균 POP 61.2%, 평균기온 24.8°C, PCP가 mm 단위 강수량,
#           적설 없음, SKY는 247건 전부 4  → 비
#   PTY=4 — n=16,  평균 POP 60.0%, 평균기온 30.1°C(가장 더움), PCP 3~9mm,
#           SKY가 3인 경우도 2건  → 소나기(부분운량에서도 발생하는 대류성 강수)
# 2(비/눈)·3(눈)은 9월 표본이라 관측하지 못했다. 그래도 위 이유로 안전하다.
PRECIPITATION_OCTAS = MAX_OCTAS

# 한국 표준시의 기준 자오선(135°E)은 utcoffset에서 끌어낸다 — 특정 시간대를
# 상수로 박지 않기 위해서다. 지구 한 바퀴 360°를 24시간으로 나눈 값.
DEGREES_PER_HOUR = 15.0


class UnknownSkyCodeError(DomainError):
    """모르는 하늘상태 코드. 감쇠를 추측하지 않고 호출자에게 넘긴다.

    이 저장소는 충전소 ``stat`` 코드에서 문서에 없는 값이 11.9%를 차지하는
    일을 이미 겪었다. 그럴듯한 기본값을 매기면 틀린 줄도 모르고 쓰게 된다.
    """


def _day_angle_rad(when: datetime) -> float:
    """Spencer의 일각(day angle) ``B = 2π(n−1)/365``. n은 연중 일수."""
    return 2.0 * pi * (when.timetuple().tm_yday - 1) / 365.0


def declination_deg(when: datetime) -> float:
    """태양 적위(도). Spencer (1971)."""
    b = _day_angle_rad(when)
    rad = (
        0.006918
        - 0.399912 * cos(b)
        + 0.070257 * sin(b)
        - 0.006758 * cos(2 * b)
        + 0.000907 * sin(2 * b)
        - 0.002697 * cos(3 * b)
        + 0.001480 * sin(3 * b)
    )
    return degrees(rad)


def equation_of_time_min(when: datetime) -> float:
    """균시차(분). Spencer (1971).

    지구 궤도가 타원이고 자전축이 기울어 있어 '진태양시'와 '평균태양시'가
    최대 ±16분 어긋난다.
    """
    b = _day_angle_rad(when)
    return 229.18 * (
        0.000075
        + 0.001868 * cos(b)
        - 0.032077 * sin(b)
        - 0.014615 * cos(2 * b)
        - 0.040849 * sin(2 * b)
    )


def eccentricity_factor(when: datetime) -> float:
    """지구-태양 거리 보정 ``E₀``. Spencer (1971).

    1월(근일점)에 1.034, 7월(원일점)에 0.967 — 대기권 밖 일사량은 겨울이
    3% 높다. 그래도 고도각 차이가 압도적이라 여름 정오가 훨씬 세다.
    """
    b = _day_angle_rad(when)
    return (
        1.000110
        + 0.034221 * cos(b)
        + 0.001280 * sin(b)
        + 0.000719 * cos(2 * b)
        + 0.000077 * sin(2 * b)
    )


def solar_elevation_deg(lat: float, lng: float, when: datetime) -> float:
    """태양 고도각(도). 지평선 아래면 음수다.

    ``when``은 타임존을 가진 시각이어야 한다 — 어느 자오선 기준의 시계인지
    모르면 남중 시각을 정할 수 없다. 표준 자오선은 ``utcoffset()``에서 끌어내
    KST(135°E)든 다른 시간대든 같은 식으로 처리한다.
    """
    offset = when.utcoffset()
    if offset is None:
        raise ValueError("타임존이 있는 시각이어야 합니다 (naive datetime 불가)")

    standard_meridian_deg = offset.total_seconds() / 3600.0 * DEGREES_PER_HOUR
    # 진태양시 = 시계시각 + 경도차 보정 + 균시차
    clock_hours = when.hour + when.minute / 60.0 + when.second / 3600.0
    correction_min = 4.0 * (lng - standard_meridian_deg) + equation_of_time_min(when)
    solar_hours = clock_hours + correction_min / 60.0

    hour_angle = radians(DEGREES_PER_HOUR * (solar_hours - 12.0))
    phi = radians(lat)
    delta = radians(declination_deg(when))

    sin_elevation = sin(phi) * sin(delta) + cos(phi) * cos(delta) * cos(hour_angle)
    # 부동소수 오차로 |x|>1이 되면 asin이 터진다.
    return degrees(asin(max(-1.0, min(1.0, sin_elevation))))


def air_mass(elevation_deg: float) -> float:
    """상대 대기질량. Kasten & Young (1989). 고도각이 0 이하면 의미가 없다."""
    if elevation_deg <= 0.0:
        raise ValueError("해가 지평선 위에 있어야 합니다")
    return 1.0 / (
        sin(radians(elevation_deg))
        + 0.50572 * (elevation_deg + 6.07995) ** -1.6364
    )


def clear_sky_ghi_wm2(lat: float, lng: float, when: datetime) -> float:
    """맑은 날 수평면 전일사량(W/m²). 해가 지평선 아래면 0."""
    elevation = solar_elevation_deg(lat, lng, when)
    if elevation <= 0.0:
        return 0.0

    extraterrestrial = SOLAR_CONSTANT_WM2 * eccentricity_factor(when)
    direct_normal = extraterrestrial * ATMOSPHERIC_TRANSMITTANCE ** (
        air_mass(elevation) ** 0.678
    )
    return direct_normal * sin(radians(elevation)) * DIFFUSE_FACTOR


def is_precipitating(pty: str) -> bool:
    """PTY가 강수를 가리키는가.

    빈 문자열은 '값이 없다'는 뜻이므로 강수로 보지 않고 SKY에 맡긴다 —
    응답에 PTY가 실제로 실려 있는지는 호출자(``infra/kma_api.py``)가 본다.
    """
    return pty.strip() not in ("", "0")


def cloud_transmittance(sky: str, pty: str) -> float:
    """구름·강수 투과율 (0, 1]. 맑은날 일사량에 곱할 값이다.

    강수 중이면 SKY가 무엇이든 전운량을 최대로 본다 — 두 값이 어긋날 때
    '비가 오고 있다'는 사실이 '맑음'보다 강한 증거다.
    """
    if is_precipitating(pty):
        octas = PRECIPITATION_OCTAS
    else:
        code = sky.strip()
        if code not in SKY_OCTAS:
            raise UnknownSkyCodeError(f"모르는 하늘상태(SKY) 코드입니다: {sky!r}")
        octas = SKY_OCTAS[code]

    return 1.0 - CLOUD_ATTENUATION_A * (octas / MAX_OCTAS) ** CLOUD_ATTENUATION_B


def ghi_wm2(lat: float, lng: float, when: datetime, sky: str, pty: str) -> float:
    """예보를 반영한 수평면 전일사량(W/m²).

    밤에는 구름 상태를 볼 것도 없이 0이다 — 모르는 SKY 코드로 예외가 나는
    일도 밤에는 일어나지 않는다.
    """
    clear = clear_sky_ghi_wm2(lat, lng, when)
    if clear <= 0.0:
        return 0.0
    return clear * cloud_transmittance(sky, pty)


def output_index(ghi: float) -> float:
    """일사량을 STC(1000 W/m²) 기준 0~1 지수로. 1.0 = 패널 정격 조건."""
    return ghi / STC_IRRADIANCE_WM2
