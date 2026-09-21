"""두 좌표 사이의 거리와, 그 반경을 감싸는 바운딩 박스.

``domain``에 두는 이유: 이 계산은 요청도 DB도 모르는 순수 함수다. 이 패키지의
규칙("웹·DB를 import하지 않는다")을 그대로 만족하고, 서버 없이 테스트된다.
요금 계산 전용 패키지처럼 보이지만 패키지를 가르는 기준은 주제가 아니라
의존 방향이다 — 여기서 갈라 ``geo`` 패키지를 따로 만들면 같은 규칙을 가진
디렉터리가 두 개가 된다.

``api/``에 두지 않은 이유: 거리 계산이 라우터에 묻어 있으면 서버를 띄우지 않고는
검증할 수 없고, 나중에 수집기 쪽에서 같은 계산이 필요해질 때 라우터를 import하게
된다.
"""

from __future__ import annotations

from math import asin, cos, degrees, radians, sin, sqrt

# IUGG 평균 지구 반지름(m). 지구는 타원체라 어떤 상수를 써도 근사지만,
# 반경 수 km 조회에서 오차는 0.5% 미만이다.
EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 사이의 대원 거리(m).

    평면 근사(피타고라스)가 아니라 하버사인을 쓰는 이유는 정확도보다 경계
    처리다 — 평면 근사는 경도 폭을 위도별로 보정하지 않아 위도가 다른 두 점의
    거리를 과대평가한다.
    """
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi = phi2 - phi1
    delta_lambda = radians(lng2 - lng1)

    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def bounding_box(lat: float, lng: float, radius_m: float) -> tuple[float, float, float, float]:
    """반경 원을 감싸는 최소 사각형 ``(min_lat, min_lng, max_lat, max_lng)``.

    DB 1차 필터용이다. 인덱스를 타는 범위 비교로 후보를 좁힌 다음, 정확한
    거리는 그 후보에 대해서만 계산한다. 박스는 원보다 크므로(모서리) 여기서
    걸러진 것은 원 밖이 확실하고, 통과한 것 중 원 밖인 것은 거리 계산이 버린다.

    경도 폭은 위도에 따라 줄어들므로 ``cos(lat)``으로 나눈다. 극에 가까우면
    그 값이 0으로 수렴해 폭이 발산하니 경도 전체로 잘라낸다 — 한국 좌표에서는
    일어나지 않지만, 위경도를 그대로 받는 공개 엔드포인트라 입력으로는 들어온다.
    """
    lat_delta = degrees(radius_m / EARTH_RADIUS_M)
    min_lat = max(lat - lat_delta, -90.0)
    max_lat = min(lat + lat_delta, 90.0)

    # 박스의 위·아래 변 중 적도에서 먼 쪽이 경도 폭이 가장 넓다. 그쪽을 기준으로
    # 잡아야 박스가 원을 온전히 덮는다.
    widest_lat = max(abs(min_lat), abs(max_lat))
    cos_lat = cos(radians(widest_lat))
    if cos_lat <= 1e-12:
        return min_lat, -180.0, max_lat, 180.0

    lng_delta = lat_delta / cos_lat
    if lng_delta >= 180:
        return min_lat, -180.0, max_lat, 180.0

    return min_lat, lng - lng_delta, max_lat, lng + lng_delta
