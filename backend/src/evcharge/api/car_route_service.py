"""와트잇 경로 위 충전소 찾기 (BE-7). 계약: docs/car-api.md "경로 위 충전소 찾기" 절.

장거리 이동 중에 도착 예상 잔량이 모자라면, 경로 근처에서 지금 비어 있는 급속 충전기를
경로 순서대로 골라 경유지로 넣게 한다(충전 실패 피하기, 편의 1순위).

경로는 "현재 위치 → 앱이 보낸 경로 지점 → 목적지" 꺾은선 근사다(``domain/route.py``).
충전기 상태 판정과 출력 계산은 ``GET /api/chargers``와 같은 코드다(``routes/chargers.py``).
숫자는 전부 여기서 계산한 값이고, 문장도 서버 템플릿이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session as DbSession

from ..domain.route import Point, corridor_boxes, project, route_length_m
from ..infra.models import ChargerCache
from .car_plan_service import spoken_distance, spoken_percent
from .routes.chargers import cache_is_empty, charger_summary, matching_count, rows_in_boxes
from .schemas import (
    AddWaypointAction,
    CarRouteChargersRequest,
    CarRouteChargersResponse,
    RouteChargerOut,
)

MAX_RESULTS = 5
# 공공 API에서 온 충전소 이름을 응답과 Claude에 실을 때의 최대 길이
MAX_NAME = 40
FAST_KW = 50

ASSUME_ROUTE = "경로는 도로가 아니라 현재 위치, 경로 지점, 목적지를 이은 직선 근사예요."
ASSUME_STATUS = "충전기 상태는 최근 수집 기준이에요(실시간이 아닐 수 있어요)."
ASSUME_ESTIMATE = (
    "충전소 도착 잔량은 내비의 남은 거리와 도착 예상 잔량으로 거리에 비례해 추정했어요."
)
NO_COVERAGE = "이 구간은 충전소 정보가 없을 수 있어요(수집 지역 밖)."
NOT_COLLECTED = "충전소 정보를 아직 수집하지 않았습니다. 잠시 후 다시 시도해 주세요."


def short_name(value: object) -> str:
    """공공 API 충전소 이름. 줄바꿈을 펴고 40자로 자른다."""
    return " ".join(str(value or "").split())[:MAX_NAME]


@dataclass(frozen=True)
class _Estimate:
    """거리 비례 잔량 추정. ``scale``은 꺾은선 거리를 내비 도로 거리로 바꾸는 비율이다."""

    soc_now: float
    rate_per_m: float
    scale: float

    def soc_at(self, road_m: float) -> float:
        return round(max(0.0, self.soc_now - self.rate_per_m * road_m), 1)


def find_along_route(
    session: DbSession, payload: CarRouteChargersRequest
) -> CarRouteChargersResponse:
    """경로 근처의 충전대기·``min_kw`` 이상 충전소를 경로 순서대로 최대 5곳.

    캐시가 비어 있으면(수집 전) 503이다. ``GET /api/chargers``와 같은 규칙이다.
    """
    points: list[Point] = payload.points()
    route_m = route_length_m(points)
    corridor = payload.corridor_m

    near: list[tuple[float, float, ChargerCache]] = []  # (along, offset, row)
    for row in rows_in_boxes(session, corridor_boxes(points, corridor)):
        projection = project(points, (row.lat, row.lng))
        # 현재 위치보다 뒤에 있는 충전소는 되돌아가야 해서 뺀다.
        if projection.behind_start or projection.offset_m > corridor:
            continue
        near.append((projection.along_m, projection.offset_m, row))
    if not near and cache_is_empty(session):
        raise HTTPException(status_code=503, detail=NOT_COLLECTED)

    matching = [
        (along, offset, row, count)
        for along, offset, row in near
        if (count := matching_count(row, available_only=True, min_kw=payload.min_kw)) > 0
    ]
    matching.sort(key=lambda item: (item[0], item[1]))
    matching = matching[:MAX_RESULTS]

    estimate = _estimate(payload, route_m)
    chargers = []
    for along, offset, row, count in matching:
        _available, top_kw = charger_summary(row)
        est_soc = reachable = None
        if estimate is not None:
            est_soc = estimate.soc_at(along * estimate.scale + offset)
            reachable = est_soc >= payload.reserve_soc
        chargers.append(
            RouteChargerOut(
                station_id=row.station_id,
                name=short_name((row.data or {}).get("name")),
                lat=row.lat,
                lng=row.lng,
                along_m=round(along),
                offset_m=round(offset),
                available_count=count,
                max_kw=top_kw,
                est_soc=est_soc,
                reachable=reachable,
            )
        )

    need_charge = None if payload.arrival_soc is None else payload.arrival_soc < payload.reserve_soc
    recommended = next((c for c in chargers if c.reachable is not False), None) or (
        chargers[0] if chargers else None
    )
    scale = estimate.scale if estimate is not None else 1.0
    assumptions = [ASSUME_ROUTE, ASSUME_STATUS] + ([ASSUME_ESTIMATE] if estimate else [])
    if not near:
        coverage_note = NO_COVERAGE
    elif not matching:
        coverage_note = (
            f"경로 근처 충전소 {len(near)}곳 중 지금 비어 있는 {payload.min_kw:g}kW 이상 "
            "충전기가 없어요."
        )
    else:
        coverage_note = None

    actions = []
    if recommended is not None:
        actions.append(
            AddWaypointAction(
                station_id=recommended.station_id,
                name=recommended.name,
                lat=recommended.lat,
                lng=recommended.lng,
            )
        )
    return CarRouteChargersResponse(
        need_charge=need_charge,
        chargers=chargers,
        speech=_speech(payload, need_charge, recommended, scale),
        actions=actions,
        assumptions=assumptions,
        coverage_note=coverage_note,
        route_m=round(route_m),
    )


def _estimate(payload: CarRouteChargersRequest, route_m: float) -> _Estimate | None:
    """세 값(soc_now, arrival_soc, remain_distance_m)이 다 있을 때만 추정한다.

    소모율 = (soc_now − arrival_soc) / remain_distance_m (%/m). 내리막·회생으로 도착
    잔량이 더 높으면 0으로 본다. 꺾은선은 도로보다 짧으니, 충전소까지의 꺾은선 거리에
    ``remain_distance_m / route_m``을 곱해 도로 거리로 맞춘다(목적지에서 추정이 내비
    도착 예상 잔량과 같아진다).
    """
    if payload.arrival_soc is None or payload.remain_distance_m is None:
        return None
    rate = max(0.0, (payload.soc_now - payload.arrival_soc) / payload.remain_distance_m)
    scale = payload.remain_distance_m / route_m if route_m > 0 else 1.0
    return _Estimate(soc_now=payload.soc_now, rate_per_m=rate, scale=scale)


def _speech(
    payload: CarRouteChargersRequest,
    need_charge: bool | None,
    recommended: RouteChargerOut | None,
    scale: float,
) -> str:
    kind = "급속충전기" if payload.min_kw >= FAST_KW else "충전기"
    arrival = spoken_percent(payload.arrival_soc) if payload.arrival_soc is not None else None

    if need_charge is False:
        return f"도착할 때 배터리가 {arrival} 남아요. 충전 없이 가셔도 돼요."

    lead = f"이대로면 도착할 때 배터리가 {arrival}예요. " if need_charge else ""
    if recommended is None:
        return f"{lead}경로 근처에 지금 비어 있는 {kind}를 찾지 못했어요."

    distance = spoken_distance(recommended.along_m * scale)
    sentence = (
        f"{lead}{distance} 앞 {recommended.name or '이름 없는 충전소'}에 "
        f"비어 있는 {kind}가 {recommended.available_count}대 있어요."
    )
    if recommended.reachable is False and recommended.est_soc is not None:
        low = spoken_percent(recommended.est_soc)
        sentence += f" 가는 동안 배터리가 {low}까지 내려갈 수 있어요."
    return f"{sentence} 경유지로 넣을까요?"
