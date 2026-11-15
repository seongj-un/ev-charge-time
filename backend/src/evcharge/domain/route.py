"""경로 근사 위의 거리 계산 (와트잇 BE-7, 경로 위 충전소 찾기).

Pleos NaviHelper는 경로 전체 선형(polyline)을 주지 않는다. 그래서 "현재 위치 → 앱이
보낸 경로 지점들 → 목적지"를 이은 꺾은선을 경로로 본다. 도로를 따라간 거리가 아니라
근사다.

점 하나를 꺾은선에 투영해 두 값을 낸다.

- ``offset_m``: 경로까지 가장 가까운 거리(옆으로 벗어난 정도)
- ``along_m``: 출발점부터 그 투영 지점까지 꺾은선을 따라간 거리

선분마다 그 선분의 중간 위도에서 등장방형(equirectangular) 평면으로 펴서 투영한다.
corridor가 10km 이하라 이 근사의 오차는 무시할 만하다. 선분 길이와 끝점 거리는
하버사인으로 잰다. 날짜변경선을 건너는 선분은 이 평면에서 지구를 반대로 도는
선분이 되므로 요청 검증에서 막는다(``api/schemas.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import cos, radians, sqrt

from .geo import EARTH_RADIUS_M, bounding_box, haversine_m

Point = tuple[float, float]  # (lat, lng)


@dataclass(frozen=True)
class Projection:
    offset_m: float
    along_m: float
    # 첫 선분의 시작점(현재 위치)보다 뒤에 있다. 돌아가야 하는 충전소다.
    behind_start: bool


def route_length_m(points: list[Point]) -> float:
    return sum(haversine_m(*a, *b) for a, b in pairwise(points))


def project(points: list[Point], target: Point) -> Projection:
    """``target``을 꺾은선 ``points``(2개 이상)에 투영한다. 가장 가까운 선분을 고른다."""
    best: Projection | None = None
    walked = 0.0
    for index, (start, end) in enumerate(pairwise(points)):
        length = haversine_m(*start, *end)
        t = _segment_parameter(start, end, target)
        clamped = min(max(t, 0.0), 1.0)
        if clamped == 0.0:
            offset = haversine_m(*start, *target)
        elif clamped == 1.0:
            offset = haversine_m(*end, *target)
        else:
            offset = _planar_offset(start, end, target, clamped)
        candidate = Projection(
            offset_m=offset,
            along_m=walked + clamped * length,
            behind_start=index == 0 and t < 0,
        )
        if best is None or candidate.offset_m < best.offset_m:
            best = candidate
        walked += length
    if best is None:
        raise ValueError("경로에는 점이 2개 이상 있어야 합니다.")
    return best


Box = tuple[float, float, float, float]  # (min_lat, min_lng, max_lat, max_lng)


def corridor_boxes(points: list[Point], corridor_m: float) -> list[Box]:
    """선분마다 corridor만큼 넓힌 사각형 ``(min_lat, min_lng, max_lat, max_lng)``. DB 1차 필터용.

    꺾은선 전체를 감싸는 사각형 하나 대신 선분마다 따로 둔다. 대각선으로 긴 경로에서
    전체 사각형은 경로와 먼 충전소까지 잔뜩 끌어온다.
    """
    boxes = []
    for start, end in pairwise(points):
        a = bounding_box(start[0], start[1], corridor_m)
        b = bounding_box(end[0], end[1], corridor_m)
        boxes.append((min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])))
    return boxes


def _xy(origin: Point, point: Point, cos_lat: float) -> tuple[float, float]:
    x = radians(point[1] - origin[1]) * cos_lat * EARTH_RADIUS_M
    y = radians(point[0] - origin[0]) * EARTH_RADIUS_M
    return x, y


def _segment_parameter(start: Point, end: Point, target: Point) -> float:
    """선분 위 투영 위치(0=시작, 1=끝, 범위 밖이면 그 밖의 값). 길이 0인 선분은 0."""
    cos_lat = cos(radians((start[0] + end[0]) / 2))
    bx, by = _xy(start, end, cos_lat)
    px, py = _xy(start, target, cos_lat)
    squared = bx * bx + by * by
    if squared == 0:
        return 0.0
    return (px * bx + py * by) / squared


def _planar_offset(start: Point, end: Point, target: Point, t: float) -> float:
    cos_lat = cos(radians((start[0] + end[0]) / 2))
    bx, by = _xy(start, end, cos_lat)
    px, py = _xy(start, target, cos_lat)
    dx, dy = px - t * bx, py - t * by
    return sqrt(dx * dx + dy * dy)
