"""기상청 단기예보 격자(LCC) 변환.

알려진 좌표로 검증한다. 가장 확실한 기준점은 **서울 (60, 127)** 이다 — 기상청
활용가이드의 예제 좌표이자, 이 프로젝트에서 실제로 호출해 정상 응답
(``resultCode=00 NORMAL_SERVICE``)을 받은 격자다.
"""

from __future__ import annotations

import pytest

from evcharge.domain.kma_grid import GRID_MAX_NX, GRID_MAX_NY, grid_to_latlng, latlng_to_grid

# (위도, 경도, nx, ny, 설명)
#
# 서울 (60, 127)이 가장 단단한 기준점이다 — 기상청 예제 격자이자 이 프로젝트가
# 실제 호출로 정상 응답을 받은 좌표다.
#
# 부산 (98, 76)·제주 (53, 38)은 기상청 격자 좌표표에 실린 값으로, 서울 하나만
# 맞추는 상수 조합은 여럿 있을 수 있으므로 **투영 상수를 독립적으로 교차
# 검증**한다. 세 점이 동시에 맞으려면 표준위도·기준점·격자간격이 모두 맞아야 한다.
KNOWN = [
    (37.5665, 126.9780, 60, 127, "서울시청 — 기상청 예제 격자"),
    (35.1798, 129.0750, 98, 76, "부산시청 — 격자 좌표표"),
    (33.4996, 126.5312, 53, 38, "제주시청 — 격자 좌표표"),
]


@pytest.mark.parametrize("lat,lng,nx,ny,label", KNOWN, ids=[k[4] for k in KNOWN])
def test_known_coordinates_map_to_published_grid(lat, lng, nx, ny, label):
    assert latlng_to_grid(lat, lng) == (nx, ny), label


def test_grid_is_stable_across_the_whole_cell():
    """같은 5km 격자 안에서는 조금 움직여도 같은 (nx, ny)가 나와야 한다.

    격자 경계에 걸친 좌표를 기준점으로 삼으면 상수를 손볼 때마다 테스트가
    흔들리므로, 기준점이 셀 한가운데에 있는지도 함께 본다.
    """
    nx, ny = latlng_to_grid(37.5665, 126.9780)

    # 약 ±1km. 5km 격자의 중앙 근처라면 같은 셀에 머문다.
    for dlat, dlng in ((0.009, 0.0), (-0.009, 0.0), (0.0, 0.011), (0.0, -0.011)):
        assert latlng_to_grid(37.5665 + dlat, 126.9780 + dlng) == (nx, ny)


def test_round_trip_returns_to_the_same_cell():
    """격자 → 위경도 → 격자가 제자리로 돌아온다 (역변환이 정변환의 역이다)."""
    for nx, ny in ((60, 127), (58, 74), (98, 76), (52, 38), (89, 90)):
        lat, lng = grid_to_latlng(nx, ny)
        assert latlng_to_grid(lat, lng) == (nx, ny)


def test_grid_centre_is_inside_korea():
    """나주 근처 격자의 중심이 한반도 남서부 좌표로 돌아온다."""
    lat, lng = grid_to_latlng(58, 74)

    assert 34.5 < lat < 35.5
    assert 126.0 < lng < 127.5


def test_out_of_range_coordinates_are_rejected():
    """격자 밖(예: 적도 한복판)은 값을 지어내지 말고 거절한다.

    기상청 격자는 한반도만 덮는다. 범위를 벗어난 좌표에 대해 형식적으로
    계산된 nx/ny를 돌려주면, 그 격자로 API를 불러 NO_DATA를 받고서야
    잘못을 알게 된다.
    """
    for lat, lng in ((0.0, 0.0), (37.5, 0.0), (-33.9, 151.2)):
        with pytest.raises(ValueError):
            latlng_to_grid(lat, lng)


def test_grid_bounds_are_exposed_for_validation():
    """격자 범위 상수가 실제로 한반도 격자 크기(149×253)와 맞는지."""
    assert GRID_MAX_NX == 149
    assert GRID_MAX_NY == 253
