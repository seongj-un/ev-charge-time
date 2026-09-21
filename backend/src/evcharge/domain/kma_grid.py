"""기상청 단기예보 격자(위경도 ↔ nx·ny) 변환 (F-09).

기상청은 전국을 5km 격자로 자르고 예보를 격자 번호로 제공한다. 단기예보 API는
위경도를 받지 않으므로, 지역 좌표를 격자 번호로 옮기는 변환이 반드시 필요하다.

투영은 **Lambert Conformal Conic(LCC)** 이고, 아래 상수는 기상청이 공개한 격자
정의(표준위도 30°N·60°N, 기준점 38°N/126°E, 기준점 격자 (43, 136), 격자 간격
5km, 지구 반경 6371.00877km)를 그대로 옮긴 것이다.

``geo.py``가 아니라 별도 모듈인 이유: ``geo.py``의 하버사인·바운딩 박스는
좌표계와 무관한 일반 계산이고 F-07 반경 조회가 쓰지만, 이쪽은 **기상청이 정한
투영 파라미터**에 묶인 값이다. 두 상수 묶음이 한 파일에 섞이면 "이 상수는 어느
쪽 것인가"를 매번 되짚어야 한다. 계층(``domain``, 순수 계산)은 같다.

검증: 서울 (37.5665, 126.9780) → **(60, 127)**. 기상청 활용가이드의 예제 격자이자
이 프로젝트가 실제 호출로 정상 응답을 받은 좌표다.
"""

from __future__ import annotations

from math import atan, atan2, cos, floor, log, pi, sin, sqrt, tan

# ── 기상청이 공개한 격자 정의 ────────────────────────────────────────────
EARTH_RADIUS_KM = 6371.00877  # 지도 투영에 쓰는 지구 반경
GRID_KM = 5.0  # 격자 간격
STANDARD_LAT1_DEG = 30.0  # 표준 위도 1
STANDARD_LAT2_DEG = 60.0  # 표준 위도 2
ORIGIN_LNG_DEG = 126.0  # 기준점 경도
ORIGIN_LAT_DEG = 38.0  # 기준점 위도
ORIGIN_NX = 43  # 기준점 X 격자
ORIGIN_NY = 136  # 기준점 Y 격자

# 격자 크기(149×253). 한반도 밖 좌표를 걸러내는 데 쓴다 — 변환식 자체는 지구
# 어디서든 형식적으로 값을 내놓기 때문에, 범위 검사를 하지 않으면 엉뚱한 격자로
# API를 불러 NO_DATA를 받고서야 잘못을 알게 된다.
GRID_MAX_NX = 149
GRID_MAX_NY = 253

_DEG = pi / 180.0


def _projection() -> tuple[float, float, float]:
    """LCC 투영 상수 ``(sn, sf, ro)``. 입력과 무관하므로 매번 같은 값이다."""
    re = EARTH_RADIUS_KM / GRID_KM
    slat1 = STANDARD_LAT1_DEG * _DEG
    slat2 = STANDARD_LAT2_DEG * _DEG
    olat = ORIGIN_LAT_DEG * _DEG

    sn = tan(pi * 0.25 + slat2 * 0.5) / tan(pi * 0.25 + slat1 * 0.5)
    sn = log(cos(slat1) / cos(slat2)) / log(sn)

    sf = tan(pi * 0.25 + slat1 * 0.5)
    sf = sf**sn * cos(slat1) / sn

    ro = tan(pi * 0.25 + olat * 0.5)
    ro = re * sf / ro**sn
    return sn, sf, ro


_SN, _SF, _RO = _projection()


def latlng_to_grid(lat: float, lng: float) -> tuple[int, int]:
    """위경도 → 기상청 격자 ``(nx, ny)``.

    격자 밖 좌표는 ``ValueError``다. "형식적으로는 계산되지만 예보가 없는"
    좌표를 조용히 통과시키지 않는다.
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"위도가 범위를 벗어났습니다: {lat}")
    if not -180.0 <= lng <= 180.0:
        raise ValueError(f"경도가 범위를 벗어났습니다: {lng}")

    re = EARTH_RADIUS_KM / GRID_KM
    ra = tan(pi * 0.25 + lat * _DEG * 0.5)
    if ra <= 0.0:
        # 남극 근처. 아래 거듭제곱이 정의되지 않는다.
        raise ValueError(f"기상청 격자 범위 밖입니다: lat={lat}, lng={lng}")
    ra = re * _SF / ra**_SN

    theta = lng * _DEG - ORIGIN_LNG_DEG * _DEG
    # 날짜변경선을 건너뛰는 입력이 반대편 격자로 접히지 않게 [-π, π]로 맞춘다.
    if theta > pi:
        theta -= 2.0 * pi
    if theta < -pi:
        theta += 2.0 * pi
    theta *= _SN

    nx = floor(ra * sin(theta) + ORIGIN_NX + 0.5)
    ny = floor(_RO - ra * cos(theta) + ORIGIN_NY + 0.5)

    if not (1 <= nx <= GRID_MAX_NX and 1 <= ny <= GRID_MAX_NY):
        raise ValueError(
            f"기상청 격자 범위 밖입니다: lat={lat}, lng={lng} → (nx={nx}, ny={ny})"
        )
    return nx, ny


def grid_to_latlng(nx: int, ny: int) -> tuple[float, float]:
    """격자 ``(nx, ny)`` → 그 격자 **중심**의 위경도.

    응답에 "어느 지점을 대표로 썼는지"를 실어 주기 위해 쓴다. 정변환의 역이라
    왕복하면 같은 격자로 돌아온다.
    """
    re = EARTH_RADIUS_KM / GRID_KM
    xn = nx - ORIGIN_NX
    yn = _RO - ny + ORIGIN_NY

    ra = sqrt(xn * xn + yn * yn)
    if _SN < 0.0:
        ra = -ra
    if ra == 0.0:
        # 투영 원점(극). 한반도 격자에서는 나오지 않지만 0으로 나누지 않게 막는다.
        return 90.0, ORIGIN_LNG_DEG

    lat_rad = 2.0 * atan((re * _SF / ra) ** (1.0 / _SN)) - pi * 0.5

    theta = 0.0 if xn == 0.0 and yn == 0.0 else atan2(xn, yn)
    lng_rad = theta / _SN + ORIGIN_LNG_DEG * _DEG

    return lat_rad / _DEG, lng_rad / _DEG

