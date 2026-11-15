"""``domain/route.py``: 꺾은선 투영(offset, along), 길이, 선분별 사각형."""

from __future__ import annotations

import pytest

from evcharge.domain.geo import haversine_m
from evcharge.domain.route import (
    Route,
    clean_route,
    corridor_boxes,
    project,
    query_boxes,
    route_length_m,
)

# 나주 빛가람동에서 북쪽으로 약 11km (위도 0.1도 ≈ 11.1km)
START = (35.0, 126.8)
NORTH = (35.1, 126.8)
NORTH_EAST = (35.1, 126.9)


def test_point_beside_a_straight_route():
    # 시작에서 북쪽으로 5.56km, 동쪽으로 약 1.82km(경도 0.02도 × cos 35°)
    projection = project([START, NORTH], (35.05, 126.82))

    assert projection.along_m == pytest.approx(haversine_m(*START, 35.05, 126.8), rel=1e-3)
    assert projection.offset_m == pytest.approx(haversine_m(35.05, 126.8, 35.05, 126.82), rel=1e-3)
    assert projection.behind_start is False


def test_point_behind_the_start_is_flagged_and_measured_to_the_start():
    behind = (34.98, 126.8)

    projection = project([START, NORTH], behind)

    assert projection.behind_start is True
    assert projection.along_m == 0
    assert projection.offset_m == pytest.approx(haversine_m(*START, *behind))


def test_point_past_the_destination_is_measured_to_the_destination():
    past = (35.12, 126.8)

    projection = project([START, NORTH], past)

    assert projection.behind_start is False
    assert projection.along_m == pytest.approx(route_length_m([START, NORTH]))
    assert projection.offset_m == pytest.approx(haversine_m(*NORTH, *past))


def test_along_adds_earlier_segments_and_picks_the_nearest_segment():
    route = [START, NORTH, NORTH_EAST]
    # 둘째 선분(동쪽으로 가는 길) 중간 바로 아래
    target = (35.099, 126.85)

    projection = project(route, target)

    first = haversine_m(*START, *NORTH)
    second_half = haversine_m(*NORTH, 35.1, 126.85)
    assert projection.along_m == pytest.approx(first + second_half, rel=1e-3)
    assert projection.offset_m == pytest.approx(111.2, rel=0.02)


def test_zero_length_segment_does_not_divide_by_zero():
    projection = project([START, START, NORTH], (35.05, 126.8))

    assert projection.offset_m == pytest.approx(0, abs=1)


def test_route_needs_two_points():
    with pytest.raises(ValueError):
        project([START], NORTH)


def test_route_length_and_boxes_per_segment():
    route = [START, NORTH, NORTH_EAST]

    assert route_length_m(route) == pytest.approx(
        haversine_m(*START, *NORTH) + haversine_m(*NORTH, *NORTH_EAST)
    )
    boxes = corridor_boxes(route, 3000)
    assert len(boxes) == 2
    min_lat, _min_lng, max_lat, max_lng = boxes[0]
    # 첫 선분 사각형은 동쪽 끝(126.9)까지 넓어지지 않는다
    assert max_lng < 126.84
    assert min_lat < 35.0 < 35.1 < max_lat
    assert boxes[1][1] < 126.8 < 126.9 < boxes[1][3]


ORIGIN = (35.0, 126.8)
DEST = (35.5, 126.8)


@pytest.mark.parametrize(
    "route_points",
    [
        [ORIGIN],
        [(35.0, 126.800033)],  # 3m 옆
        [(35.0 - 0.00045, 126.8)],  # 50m 뒤
        [(34.9, 126.8)],  # 지나온 출발 지점
        [(34.9, 126.8), (34.95, 126.8), (35.0, 126.8)],  # 지나온 지점 여러 개
    ],
)
def test_clean_route_drops_passed_and_merged_points(route_points):
    assert clean_route(ORIGIN, route_points, DEST) == [ORIGIN, DEST]


def test_clean_route_keeps_points_ahead_and_drops_only_those_passed():
    ahead = (35.2, 126.85)
    assert clean_route(ORIGIN, [(34.9, 126.8), ahead], DEST) == [ORIGIN, ahead, DEST]
    # 아직 첫 경로 지점에 닿기 전이면 그대로 둔다
    assert clean_route(ORIGIN, [ahead], DEST) == [ORIGIN, ahead, DEST]


def test_clean_route_keeps_the_destination_over_a_point_next_to_it():
    near_dest = (35.5 - 0.0002, 126.8)  # 22m

    assert clean_route(ORIGIN, [near_dest], DEST) == [ORIGIN, DEST]


def test_clean_route_at_a_middle_route_point_keeps_the_points_after_it():
    passed = (34.9, 126.8)
    turn = (35.0, 126.8)  # 지금 위치가 이 경로 지점이다
    after = (35.0, 126.9)

    assert clean_route(ORIGIN, [passed, turn, after], DEST) == [ORIGIN, after, DEST]


def test_clean_route_with_destination_next_to_origin_has_no_behind():
    route = Route.of(clean_route(ORIGIN, [], (35.0001, 126.8)))

    assert len(route.points) == 2
    assert route.project((34.99, 126.8)).behind_start is False


def test_segment_boxes_skip_only_segments_farther_than_the_corridor():
    rng = __import__("random").Random(3)
    points = [ORIGIN, (35.2, 126.9), (35.3, 126.7), DEST]
    plain = Route.of(points)
    boxed = Route.of(points, corridor_m=3000)

    for _ in range(500):
        target = (rng.uniform(34.95, 35.55), rng.uniform(126.6, 127.0))
        full = plain.project(target)
        fast = boxed.project(target)
        if full.offset_m <= 3000:
            assert fast == full
        else:
            assert fast is None or fast.offset_m > 3000


def test_query_boxes_split_long_segments_in_route_order():
    boxes = query_boxes([ORIGIN, DEST], 1000)  # 약 55.6km → 10km 조각 6개

    assert len(boxes) == 6
    assert [round(b[0], 2) for b in boxes] == sorted(round(b[0], 2) for b in boxes)
    assert boxes[0][0] < 35.0 and boxes[-1][2] > 35.5
