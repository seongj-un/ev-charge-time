"""위경도 거리·바운딩 박스 (F-07 주변 충전소가 쓴다).

이 테스트는 DB도 서버도 띄우지 않는다 — domain은 순수 계산 계층이다.
"""

from __future__ import annotations

import math

from evcharge.domain.geo import EARTH_RADIUS_M, bounding_box, haversine_m

# 나주 빛가람동 언저리. 대회 지역이라 실제로 쓰일 좌표대에서 검증한다.
NAJU = (35.0175, 126.7905)

# 위도 1도의 길이. 자오선은 대원이므로 반지름만으로 정해진다.
ONE_DEGREE_LAT_M = 2 * math.pi * EARTH_RADIUS_M / 360


def test_same_point_is_zero():
    assert haversine_m(*NAJU, *NAJU) == 0


def test_one_degree_of_latitude_is_about_111km():
    lat, lng = NAJU
    distance = haversine_m(lat, lng, lat + 1, lng)

    # 자오선 한 도 = 2πR/360. 오차 1m 안에 들어와야 한다.
    assert abs(distance - ONE_DEGREE_LAT_M) < 1


def test_seoul_to_busan_is_about_325km():
    # 서울시청 → 부산시청. 대원거리로 흔히 인용되는 325km 언저리.
    distance = haversine_m(37.5665, 126.9780, 35.1796, 129.0756)

    assert 320_000 < distance < 330_000


def test_is_symmetric():
    a = NAJU
    b = (35.1595, 126.8526)  # 광주 상무지구

    assert haversine_m(*a, *b) == haversine_m(*b, *a)


def test_short_distance_is_accurate_to_the_metre():
    lat, lng = NAJU
    # 위도로 0.001도 = 약 111.2m. 가까운 거리에서 반올림 오차가 새지 않는지 본다.
    distance = haversine_m(lat, lng, lat + 0.001, lng)

    assert abs(distance - ONE_DEGREE_LAT_M / 1000) < 0.01


def test_bounding_box_contains_the_circle_edge():
    lat, lng = NAJU
    radius = 2000
    min_lat, min_lng, max_lat, max_lng = bounding_box(lat, lng, radius)

    # 정확히 반경만큼 동서남북으로 간 점은 전부 박스 안에 있어야 한다.
    # (박스가 원보다 작으면 DB 1차 필터에서 진짜 후보가 탈락한다)
    for delta_lat, delta_lng in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        edge_lat = lat + delta_lat * radius / ONE_DEGREE_LAT_M
        edge_lng = lng + delta_lng * radius / (ONE_DEGREE_LAT_M * math.cos(math.radians(lat)))
        assert min_lat <= edge_lat <= max_lat
        assert min_lng <= edge_lng <= max_lng


def test_bounding_box_is_tight_enough_to_be_worth_it():
    lat, lng = NAJU
    min_lat, _min_lng, max_lat, _max_lng = bounding_box(lat, lng, 2000)

    # 반경의 두 배 떨어진 점은 박스 밖이어야 한다. 박스가 너무 헐거우면
    # 32,835건을 파이썬으로 끌어오지 말라는 요구가 무의미해진다.
    assert not (min_lat <= lat + 2 * 2000 / ONE_DEGREE_LAT_M <= max_lat)


def test_bounding_box_clamps_at_the_poles():
    # 극지방에서 경도 폭이 발산하지 않게 잘라낸다. 한국 좌표에서는 안 쓰이지만
    # 위경도를 그대로 받는 공개 엔드포인트라 입력으로는 들어올 수 있다.
    min_lat, min_lng, max_lat, max_lng = bounding_box(89.999, 0.0, 50_000)

    assert min_lat >= -90
    assert max_lat <= 90
    assert min_lng == -180
    assert max_lng == 180
