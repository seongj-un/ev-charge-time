"""와트잇 경로 위 충전소 찾기 (BE-7). 계약: docs/car-api.md "경로 위 충전소 찾기" 절.

장거리 이동 중에 도착 예상 잔량이 모자라면, 경로 근처에서 지금 비어 있는 급속 충전기를
경로 순서대로 골라 경유지로 넣게 한다(충전 실패 피하기, 편의 1순위).

경로는 "현재 위치 → 앱이 보낸 경로 지점 → 목적지" 꺾은선 근사다(``domain/route.py``).
충전기 상태 판정과 출력 계산은 ``GET /api/chargers``와 같은 코드다(``routes/chargers.py``).
숫자는 전부 여기서 계산한 값이고, 문장도 서버 템플릿이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session as DbSession

from ..domain.route import Route, clean_route, query_boxes
from ..infra.models import ChargerCache
from .car_plan_service import spoken_distance, spoken_percent
from .routes.chargers import (
    STATUS_UNKNOWN_NOTE,
    FreshnessLimits,
    cache_is_empty,
    charger_summary,
    matching_count,
    rows_in_boxes,
    status_age,
)
from .schemas import (
    AddWaypointAction,
    AskAction,
    CarRouteChargersRequest,
    CarRouteChargersResponse,
    RouteChargerOut,
)

MAX_RESULTS = 5
# DB에서 읽는 후보 행 수 상한. 경로 순서로 앞쪽 구간부터 읽는다(``query_boxes``).
# 전남·광주 크기 캐시(약 8천 곳)를 corridor 10km 지그재그 경로로 훑어도 계산이 0.3초
# 안에 끝나게 하는 크기다(측정값은 PR 본문).
MAX_CANDIDATE_ROWS = 3000
# 공공 API에서 온 충전소 이름을 응답과 Claude에 실을 때의 최대 길이
MAX_NAME = 40
FAST_KW = 50

ASSUME_ROUTE = "경로는 도로가 아니라 현재 위치, 경로 지점, 목적지를 이은 직선 근사예요."
ASSUME_STATUS = "충전기 상태는 최근 수집 기준이에요(실시간이 아닐 수 있어요)."
ASSUME_ESTIMATE = (
    "충전소 도착 잔량은 내비의 남은 거리와 도착 예상 잔량으로 거리에 비례해 추정했어요."
)
ASSUME_EFFICIENCY = "충전소 도착 잔량은 최근 전비와 배터리 용량으로 거리에 비례해 추정했어요."
# 내비 남은 거리가 없을 때 직선거리를 도로 거리로 바꾸는 계수. 직선거리 그대로 쓰면 도착
# 잔량이 실제보다 높게(낙관적으로) 나온다.
ROAD_FACTOR = 1.25
ASSUME_ROAD_FACTOR = "내비 남은 거리가 없어 도로 거리를 직선거리의 1.25배(도로 계수)로 잡았어요."
NO_COVERAGE = "이 구간은 충전소 정보가 없을 수 있어요(수집 지역 밖)."
TRUNCATED = "경로 근처 충전소가 많아 앞쪽 구간의 충전소만 살펴봤어요."
# 정리된 꺾은선에 이보다 긴 선분이 있으면 직선 근사의 한계를 알린다. 경유지 없는 장거리는
# 내비가 경로 모양 점을 주지 않아 직선 하나로 계산한다.
LONG_SEGMENT_M = 100_000
ASSUME_LONG_SEGMENT = (
    "경유지 사이가 먼 구간은 실제 도로가 직선에서 크게 벗어날 수 있어, 도로 옆 휴게소가 "
    "검색 범위 밖일 수 있어요."
)
NOT_COLLECTED = "충전소 정보를 아직 수집하지 않았습니다. 잠시 후 다시 시도해 주세요."


def short_name(value: object) -> str:
    """공공 API 충전소 이름. 줄바꿈을 펴고 40자로 자른다."""
    return " ".join(str(value or "").split())[:MAX_NAME]


RUNS_OUT_QUESTION = "더 가까운 충전소를 찾아볼까요?"
# 경로에서 이만큼 이상 벗어난 충전소는 문장에 벗어난 거리를 함께 말한다.
OFFSET_SPOKEN_M = 500


@dataclass(frozen=True)
class _Estimate:
    """거리 비례 잔량 추정."""

    soc_now: float
    rate_per_m: float
    assumption: str

    def soc_at(self, road_m: float) -> float:
        return round(max(0.0, self.left_at(road_m)), 1)

    def runs_out_before(self, road_m: float) -> bool:
        """가는 동안 쓰는 양이 지금 잔량 이상이다(0으로 자르기 전 값이 0 이하)."""
        return self.left_at(road_m) <= 0

    def left_at(self, road_m: float) -> float:
        return self.soc_now - self.rate_per_m * road_m


def find_along_route(
    session: DbSession, payload: CarRouteChargersRequest, now: datetime
) -> CarRouteChargersResponse:
    """경로 근처의 충전대기·``min_kw`` 이상 충전소를 경로 순서대로 최대 5곳.

    캐시가 비어 있으면(수집 전) 503이다. ``GET /api/chargers``와 같은 규칙이다.
    """
    # 지나온 경로 지점과 현재 위치에 붙은 지점을 버린 남은 경로
    route = Route.of(
        clean_route(
            (payload.origin.lat, payload.origin.lng),
            [(point.lat, point.lng) for point in payload.route_points],
            (payload.destination.lat, payload.destination.lng),
        ),
        corridor_m=payload.corridor_m,
    )
    route_m = route.length_m
    corridor = payload.corridor_m

    rows = rows_in_boxes(
        session, query_boxes(route.points, corridor), limit=MAX_CANDIDATE_ROWS + 1
    )
    truncated = len(rows) > MAX_CANDIDATE_ROWS
    near: list[tuple[float, float, ChargerCache]] = []  # (along, offset, row)
    for row in rows[:MAX_CANDIDATE_ROWS]:
        projection = route.project((row.lat, row.lng))
        # 현재 위치보다 뒤에 있는 충전소는 되돌아가야 해서 뺀다.
        if projection is None or projection.behind_start or projection.offset_m > corridor:
            continue
        near.append((projection.along_m, projection.offset_m, row))
    if not near and cache_is_empty(session):
        raise HTTPException(status_code=503, detail=NOT_COLLECTED)

    limits = FreshnessLimits.current(session)
    ages = {row.station_id: status_age(row, now, limits) for _, _, row in near}
    matching = [
        (along, offset, row, count)
        for along, offset, row in near
        if (
            count := matching_count(
                row,
                available_only=True,
                min_kw=payload.min_kw,
                status_known=ages[row.station_id].known,
            )
        )
        > 0
    ]
    # 상태가 새것이었다면 남았을 충전소: 비었을 때 "없다"와 "확인할 수 없다"를 가른다.
    hidden_by_age = not matching and any(
        matching_count(row, available_only=True, min_kw=payload.min_kw, status_known=True) > 0
        for _, _, row in near
    )
    matching.sort(key=lambda item: (item[0], item[1]))
    matching = matching[:MAX_RESULTS]

    estimate = _estimate(payload)
    # 꺾은선은 도로보다 짧다. 내비 남은 거리가 있으면 그 비율로 늘려 도로 거리로 맞춘다
    # (목적지에서 추정이 내비 도착 예상 잔량과 같아진다). 없으면 도로 계수를 곱한다.
    remain = payload.remain_distance_m
    scale = ROAD_FACTOR if remain is None else (remain / route_m if route_m > 0 else 1.0)
    chargers = []
    for along, offset, row, count in matching:
        _available, top_kw = charger_summary(row)
        distance = along * scale + offset
        est_soc = reachable = runs_out = None
        if estimate is not None:
            est_soc = estimate.soc_at(distance)
            reachable = est_soc >= payload.reserve_soc
            runs_out = estimate.runs_out_before(distance)
        chargers.append(
            RouteChargerOut(
                station_id=row.station_id,
                name=short_name((row.data or {}).get("name")),
                lat=row.lat,
                lng=row.lng,
                along_m=round(along),
                offset_m=round(offset),
                distance_m=round(distance),
                available_count=count,
                max_kw=top_kw,
                est_soc=est_soc,
                reachable=reachable,
                runs_out=runs_out,
                synced_at=ages[row.station_id].synced_at,
                status_age_min=ages[row.station_id].age_min,
                stale=ages[row.station_id].stale,
            )
        )

    # 도착 잔량: 내비 값이 있으면 그대로, 없고 전비로 추정하면 목적지까지 도로 거리로 추정
    arrival: float | None = payload.arrival_soc
    arrival_estimated = arrival_runs_out = False
    if arrival is None and estimate is not None and estimate.assumption == ASSUME_EFFICIENCY:
        arrival = estimate.soc_at(route_m * scale)
        arrival_estimated = True
        arrival_runs_out = estimate.runs_out_before(route_m * scale)
    need_charge = None if arrival is None else arrival < payload.reserve_soc
    recommended = _recommend(chargers)
    assumptions = [ASSUME_ROUTE, ASSUME_STATUS]
    if max(route.lengths) > LONG_SEGMENT_M:
        assumptions.append(ASSUME_LONG_SEGMENT)
    if remain is None:
        assumptions.append(ASSUME_ROAD_FACTOR)
    if estimate is not None:
        assumptions.append(estimate.assumption)
    if not near:
        coverage_note = NO_COVERAGE
    elif hidden_by_age:
        coverage_note = STATUS_UNKNOWN_NOTE
    elif not matching:
        coverage_note = (
            f"경로 근처 충전소 {len(near)}곳 중 지금 비어 있는 {payload.min_kw:g}kW 이상 "
            "충전기가 없어요."
        )
    else:
        coverage_note = None
    if truncated:
        coverage_note = f"{coverage_note} {TRUNCATED}" if coverage_note else TRUNCATED

    actions = []
    # 충전이 필요 없다고 말할 때는 경유지 버튼을 주지 않는다(말과 화면이 어긋난다).
    # 충전소 목록은 그대로 준다.
    # 가기 전에 바닥날 수 있는 충전소는 경유지로 넣지 않고 운전자에게 묻는다.
    actions: list[AddWaypointAction | AskAction] = []
    if recommended is not None and need_charge is not False:
        if recommended.runs_out:
            actions.append(AskAction(question=RUNS_OUT_QUESTION))
        else:
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
        speech=_speech(
            payload,
            arrival,
            arrival_estimated,
            arrival_runs_out,
            need_charge,
            recommended,
            status_unknown=hidden_by_age,
        ),
        actions=actions,
        assumptions=assumptions,
        coverage_note=coverage_note,
        route_m=round(route_m),
    )


def stale_sentence(age_min: int) -> str:
    return f"충전기 상태는 {age_min}분 전 정보예요."


def _recommend(chargers: list[RouteChargerOut]) -> RouteChargerOut | None:
    """경로 순서대로 보며, 갈 수 있는 첫 충전소 → 바닥나지 않는 첫 충전소 → 첫 충전소.

    목록 순서는 바꾸지 않는다. 추정이 없으면(``reachable`` null) 첫 충전소다.
    """
    for wanted in (
        lambda c: c.reachable is not False,
        lambda c: c.runs_out is not True,
        lambda c: True,
    ):
        found = next((c for c in chargers if wanted(c)), None)
        if found is not None:
            return found
    return None


def _estimate(payload: CarRouteChargersRequest) -> _Estimate | None:
    """충전소 도착 잔량 추정. 근거가 없으면 None(추정하지 않음).

    1. 내비: ``arrival_soc``와 ``remain_distance_m``가 다 있으면 소모율 =
       (soc_now − arrival_soc) / remain_distance_m (%/m). 내리막·회생으로 도착 잔량이 더
       높으면 0으로 본다. 내비는 이번 경로의 고도·속도를 반영하므로 먼저 쓴다.
    2. 전비: 없으면 ``efficiency_km_per_kwh``와 ``battery_capacity_wh``로
       1m당 1 / (전비 × 1000) kWh, 잔량으로는 100 / (전비 × 용량 Wh) %/m.
    """
    if payload.arrival_soc is not None and payload.remain_distance_m is not None:
        rate = max(0.0, (payload.soc_now - payload.arrival_soc) / payload.remain_distance_m)
        return _Estimate(soc_now=payload.soc_now, rate_per_m=rate, assumption=ASSUME_ESTIMATE)
    if payload.efficiency_km_per_kwh is not None and payload.battery_capacity_wh is not None:
        rate = 100 / (payload.efficiency_km_per_kwh * payload.battery_capacity_wh)
        return _Estimate(soc_now=payload.soc_now, rate_per_m=rate, assumption=ASSUME_EFFICIENCY)
    return None


def _speech(
    payload: CarRouteChargersRequest,
    arrival_soc: float | None,
    arrival_estimated: bool,
    arrival_runs_out: bool,
    need_charge: bool | None,
    recommended: RouteChargerOut | None,
    *,
    status_unknown: bool = False,
) -> str:
    """도착 잔량을 전비로 추정했으면 "전비로 추정하면"으로 시작한다(내비 값이 아님을 밝힌다).

    추정 잔량이 0 이하이면 "0%예요" 대신 "닿기 전에 바닥날 수 있어요"라고 말한다.
    0%는 "아슬아슬하게 닿는다"로 들린다.
    """
    kind = "급속충전기" if payload.min_kw >= FAST_KW else "충전기"
    arrival = spoken_percent(arrival_soc) if arrival_soc is not None else None

    if need_charge is False:
        if arrival_estimated:
            return f"전비로 추정하면 도착할 때 배터리가 {arrival} 남아요. 충전 없이 가셔도 돼요."
        return f"도착할 때 배터리가 {arrival} 남아요. 충전 없이 가셔도 돼요."

    if not need_charge:
        lead = ""
    elif arrival_runs_out:
        lead = "전비로 추정하면 목적지에 닿기 전에 배터리가 바닥날 수 있어요. "
    elif arrival_estimated:
        lead = f"전비로 추정하면 도착할 때 배터리가 {arrival}예요. "
    else:
        lead = f"이대로면 도착할 때 배터리가 {arrival}예요. "
    if recommended is None:
        if status_unknown:
            # 오래된 상태 때문에 비었다: "찾지 못했어요"(없다)가 아니라 "확인할 수 없다"다.
            return f"{lead}{STATUS_UNKNOWN_NOTE}"
        return f"{lead}경로 근처에 지금 비어 있는 {kind}를 찾지 못했어요."

    where = f"{spoken_distance(recommended.distance_m)} 앞"
    if recommended.offset_m >= OFFSET_SPOKEN_M:
        where += f", 경로에서 {spoken_distance(recommended.offset_m)} 벗어난"
    sentence = (
        f"{lead}{where} {recommended.name or '이름 없는 충전소'}에 "
        f"비어 있는 {kind}가 {recommended.available_count}대 있어요."
    )
    if recommended.stale:
        # "비어 있어요"가 몇 분 전 값인지 밝힌다(BE-10). 질문(경유지로 넣을까요?) 앞에 둔다.
        sentence += f" {stale_sentence(recommended.status_age_min)}"
    if recommended.runs_out:
        return f"{sentence} 이 충전소까지 가기 전에 배터리가 바닥날 수 있어요. {RUNS_OUT_QUESTION}"
    if recommended.reachable is False and recommended.est_soc is not None:
        low = spoken_percent(recommended.est_soc)
        sentence += f" 가는 동안 배터리가 {low}까지 내려갈 수 있어요."
    return f"{sentence} 경유지로 넣을까요?"
