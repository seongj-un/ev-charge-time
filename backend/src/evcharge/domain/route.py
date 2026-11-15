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

꺾은선은 먼저 정리한다(``clean_route``). 앱이 지나온 경로 지점이나 현재 위치와 겹치는
지점을 보내도, 현재 위치에서 시작하는 남은 경로만 남긴다. 그래야 "뒤에 있는 충전소"
판정과 경로 길이가 맞는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import ceil, cos, radians, sqrt

from .geo import EARTH_RADIUS_M, bounding_box, haversine_m

Point = tuple[float, float]  # (lat, lng)
Box = tuple[float, float, float, float]  # (min_lat, min_lng, max_lat, max_lng)

# 이 거리 안으로 이어진 점은 하나로 합친다. GPS 위치와 내비 경로 지점은 몇 m씩 어긋난다.
MERGE_M = 50.0
# 현재 위치에서 가장 가까운 선분을 찾을 때, 가장 가까운 것과 이만큼 안으로 차이 나는
# 선분 중에서는 앞쪽 선분을 고른다(경로 지점 위에 서 있으면 두 선분이 같은 거리다).
# 한계: 나중에 현재 위치 옆을 다시 지나는 경로는 좌표만으로 "지금 출발" 과 "돌아오는
# 중"을 구분할 수 없다. 그 경로가 이 거리보다 더 가까이 지나면 돌아오는 중으로 본다.
NEAREST_TIE_M = 100.0
# DB 1차 필터 사각형을 만들 때 긴 선분을 이 길이로 나눈다. 대각선 선분 하나를 감싸는
# 사각형은 선분 길이의 제곱만큼 넓어져, 경로와 먼 충전소까지 끌어온다.
QUERY_CHUNK_M = 10_000.0


@dataclass(frozen=True)
class Projection:
    offset_m: float
    along_m: float
    # 현재 위치(꺾은선 시작점)보다 뒤에 있다. 돌아가야 하는 충전소다.
    behind_start: bool


def route_length_m(points: list[Point]) -> float:
    return sum(haversine_m(*a, *b) for a, b in pairwise(points))


def clean_route(origin: Point, route_points: list[Point], destination: Point) -> list[Point]:
    """현재 위치에서 시작하는 남은 경로. 항상 ``origin``으로 시작해 ``destination``으로 끝난다.

    1. 지나온 지점 버리기: ``route_points + [destination]`` 꺾은선에서 현재 위치와 가장
       가까운 선분을 찾아, 그 선분의 시작점까지(이미 지나온 쪽)를 버린다. 현재 위치가 첫
       경로 지점보다 앞(아직 닿기 전)이면 그대로 둔다.
    2. 합치기: 바로 앞에 남긴 점과 ``MERGE_M`` 안인 점은 버린다. 목적지가 마지막 경로
       지점과 붙어 있으면 그 경로 지점 대신 목적지를 남긴다.
    """
    ahead = _drop_passed(origin, [*route_points, destination])
    cleaned = [origin]
    for index, point in enumerate(ahead):
        if haversine_m(*cleaned[-1], *point) > MERGE_M:
            cleaned.append(point)
        elif index == len(ahead) - 1:
            # 목적지는 꼭 남긴다. 현재 위치와 붙어 있으면 길이가 거의 0인 경로가 된다.
            if len(cleaned) > 1:
                cleaned[-1] = point
            else:
                cleaned.append(point)
    return cleaned


def _drop_passed(origin: Point, ahead: list[Point]) -> list[Point]:
    if len(ahead) < 2:
        return ahead
    candidates = []
    for index, (start, end) in enumerate(pairwise(ahead)):
        t = _segment_parameter(start, end, origin)
        candidates.append((index, t, _offset(start, end, origin, t)))
    nearest = min(offset for _, _, offset in candidates)
    index, t, _ = next(c for c in candidates if c[2] <= nearest + NEAREST_TIE_M)
    if index == 0 and t <= 0:
        return ahead
    return ahead[index + 1 :]


@dataclass(frozen=True)
class Route:
    """정리된 꺾은선과 선분별 길이. 충전소마다 다시 재지 않도록 한 번만 계산한다."""

    points: list[Point]
    lengths: list[float]
    # 각 선분 시작점까지의 누적 거리
    starts: list[float]
    # 선분별 corridor 사각형. 있으면 그 밖의 충전소는 그 선분에 투영하지 않는다.
    boxes: list[Box] | None = None

    @classmethod
    def of(cls, points: list[Point], corridor_m: float | None = None) -> Route:
        if len(points) < 2:
            raise ValueError("경로에는 점이 2개 이상 있어야 합니다.")
        lengths = [haversine_m(*a, *b) for a, b in pairwise(points)]
        starts = [0.0]
        for length in lengths[:-1]:
            starts.append(starts[-1] + length)
        boxes = corridor_boxes(points, corridor_m) if corridor_m is not None else None
        return cls(points=points, lengths=lengths, starts=starts, boxes=boxes)

    @property
    def length_m(self) -> float:
        return self.starts[-1] + self.lengths[-1]

    def project(self, target: Point) -> Projection | None:
        """``target``을 꺾은선에 투영한다. 가장 가까운 선분을 고른다.

        선분별 corridor 사각형이 있으면 ``target``이 든 사각형의 선분만 본다(그 밖의
        선분은 corridor보다 멀다). 어느 사각형에도 없으면 None이다.
        """
        best: Projection | None = None
        for index, (start, end) in enumerate(pairwise(self.points)):
            if self.boxes is not None and not _inside(self.boxes[index], target):
                continue
            t = _segment_parameter(start, end, target)
            clamped = min(max(t, 0.0), 1.0)
            candidate = Projection(
                offset_m=_offset(start, end, target, t),
                along_m=self.starts[index] + clamped * self.lengths[index],
                # 첫 선분(현재 위치에서 나가는 방향)의 시작점 뒤. 정리된 꺾은선의 첫 선분은
                # MERGE_M보다 길다. 그보다 짧으면(목적지가 바로 옆) 방향이 없어 판정하지 않는다.
                behind_start=index == 0 and t < 0 and self.lengths[0] > MERGE_M,
            )
            if best is None or candidate.offset_m < best.offset_m:
                best = candidate
        return best


def project(points: list[Point], target: Point) -> Projection:
    """``target``을 꺾은선 ``points``(2개 이상)에 투영한다."""
    projection = Route.of(points).project(target)
    if projection is None:  # 사각형 없이 투영하면 생기지 않는다
        raise ValueError("투영할 선분이 없습니다.")
    return projection


def corridor_boxes(points: list[Point], corridor_m: float) -> list[Box]:
    """선분마다 corridor만큼 넓힌 사각형 하나. 투영할 선분을 고를 때 쓴다."""
    return [_box(start, end, corridor_m) for start, end in pairwise(points)]


def query_boxes(points: list[Point], corridor_m: float) -> list[Box]:
    """DB 1차 필터용 사각형. 긴 선분은 ``QUERY_CHUNK_M`` 조각으로 나눠 경로 순서대로 둔다.

    순서가 경로 순서라, 행 수 상한에 걸리면 앞쪽 구간의 충전소부터 남길 수 있다.
    위경도 직선 보간으로 나눈다. 투영도 선분을 위경도 평면의 직선으로 보므로(``_xy``) 같은
    선을 따라간다.
    """
    boxes = []
    for (start, end), length in zip(pairwise(points), map(_length, pairwise(points)), strict=True):
        pieces = max(1, ceil(length / QUERY_CHUNK_M))
        for piece in range(pieces):
            a = _lerp(start, end, piece / pieces)
            b = _lerp(start, end, (piece + 1) / pieces)
            boxes.append(_box(a, b, corridor_m))
    return boxes


def _length(pair: tuple[Point, Point]) -> float:
    return haversine_m(*pair[0], *pair[1])


def _lerp(start: Point, end: Point, f: float) -> Point:
    return (start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f)


def _box(start: Point, end: Point, corridor_m: float) -> Box:
    a = bounding_box(start[0], start[1], corridor_m)
    b = bounding_box(end[0], end[1], corridor_m)
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _inside(box: Box, point: Point) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


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


def _offset(start: Point, end: Point, target: Point, t: float) -> float:
    """선분까지 최단 거리. 투영이 끝점 밖이면 그 끝점까지 하버사인."""
    if t <= 0:
        return haversine_m(*start, *target)
    if t >= 1:
        return haversine_m(*end, *target)
    cos_lat = cos(radians((start[0] + end[0]) / 2))
    bx, by = _xy(start, end, cos_lat)
    px, py = _xy(start, target, cos_lat)
    dx, dy = px - t * bx, py - t * by
    return sqrt(dx * dx + dy * dy)
