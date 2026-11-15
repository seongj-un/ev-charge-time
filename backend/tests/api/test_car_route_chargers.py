"""``POST /api/car/chargers/along-route`` (BE-7)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from evcharge.api import car_route_service
from evcharge.api.car_plan_service import spoken_distance
from evcharge.api.routes import car
from evcharge.domain.pricing import KST
from evcharge.infra.models import ChargerCache

URL = "/api/car/chargers/along-route"
# 나주에서 북쪽으로 약 55.6km(위도 0.5도). 경도 0.011도 ≈ 1.0km (위도 35도)
ORIGIN = {"lat": 35.0, "lng": 126.8}
DEST = {"lat": 35.5, "lng": 126.8}
KM_EAST = 0.011


def charger(status="2", kw=100.0, charger_id="01"):
    return {"charger_id": charger_id, "type": "04", "capacity_kw": kw, "status": status}


def station(db_session, station_id, lat, lng=126.8, *, name=None, chargers=None):
    data = {"name": name or f"{station_id} 충전소", "chargers": chargers or [charger()]}
    db_session.add(ChargerCache(station_id=station_id, data=data, lat=lat, lng=lng))
    db_session.commit()


def post(client, **body):
    return client.post(URL, json={"origin": ORIGIN, "destination": DEST, "soc_now": 60, **body})


@pytest.fixture
def stations(db_session):
    # 경로 옆 10km 지점, 동쪽 1km: 100kW 빈 충전기
    station(db_session, "A", 35.09, 126.8 + KM_EAST, chargers=[charger(kw=100.0)])
    # 30km 지점, 서쪽 2km: 50kW 빈 충전기 2대 + 7kW 빈 충전기
    station(
        db_session,
        "B",
        35.27,
        126.8 - 2 * KM_EAST,
        chargers=[
            charger(kw=50.0),
            charger(kw=50.0, charger_id="02"),
            charger(kw=7.0, charger_id="03"),
        ],
    )
    # 출발점 뒤 2km
    station(db_session, "BEHIND", 34.982)
    # 20km 지점이지만 동쪽 5km (corridor 3km 밖)
    station(db_session, "FAR", 35.18, 126.8 + 5 * KM_EAST)
    # 출력 미달, 충전 중, 같은 충전기가 두 조건을 다 못 맞추는 곳
    station(db_session, "SLOW", 35.05, chargers=[charger(kw=7.0)])
    station(db_session, "BUSY", 35.06, chargers=[charger(status="3")])
    station(
        db_session, "MIX", 35.07, chargers=[charger(kw=7.0), charger(status="3", charger_id="02")]
    )


def test_keeps_free_fast_chargers_beside_the_route_in_route_order(client, stations):
    body = post(client).json()

    assert [c["station_id"] for c in body["chargers"]] == ["A", "B"]
    first, second = body["chargers"]
    assert first["along_m"] == pytest.approx(10_000, rel=0.01)
    assert first["offset_m"] == pytest.approx(1_000, rel=0.03)
    assert second["offset_m"] == pytest.approx(2_000, rel=0.03)
    # B의 7kW 충전기는 세지 않는다
    assert (first["available_count"], first["max_kw"]) == (1, 100.0)
    assert (second["available_count"], second["max_kw"]) == (2, 50.0)
    assert first["est_soc"] is None and first["reachable"] is None
    assert body["need_charge"] is None
    assert body["route_m"] == pytest.approx(55_597, rel=0.001)
    assert body["coverage_note"] is None


def test_min_kw_and_corridor_are_parameters(client, stations):
    only_100 = post(client, min_kw=100).json()
    wide = post(client, corridor_m=6000).json()

    assert [c["station_id"] for c in only_100["chargers"]] == ["A"]
    assert "FAR" in [c["station_id"] for c in wide["chargers"]]


def test_at_most_five_in_route_order(client, db_session):
    for index in range(7):
        station(db_session, f"S{index}", 35.4 - index * 0.05)

    body = post(client).json()

    assert [c["station_id"] for c in body["chargers"]] == ["S6", "S5", "S4", "S3", "S2"]


def test_route_points_bend_the_route(client, db_session):
    # 동쪽으로 돌아가는 경로 위의 충전소: 직선 경로에서는 corridor 밖
    station(db_session, "EAST", 35.25, 126.9)
    straight = post(client).json()
    bent = post(client, route_points=[{"lat": 35.25, "lng": 126.9}]).json()

    assert straight["chargers"] == []
    assert [c["station_id"] for c in bent["chargers"]] == ["EAST"]
    assert bent["route_m"] > straight["route_m"]


ESTIMATE = {"arrival_soc": 8, "remain_distance_m": 60_000}


def test_estimates_soc_at_each_charger_in_proportion_to_road_distance(client, stations):
    body = post(client, **ESTIMATE).json()

    scale = 60_000 / body["route_m"]
    rate = (60 - 8) / 60_000
    for item in body["chargers"]:
        road = item["along_m"] * scale + item["offset_m"]
        assert item["est_soc"] == pytest.approx(60 - rate * road, abs=0.1)
        assert item["reachable"] is True
    assert body["need_charge"] is True
    assert body["assumptions"][-1].startswith("충전소 도착 잔량은")


def test_reachable_boundary_is_reserve_soc_inclusive(client, stations):
    est_b = post(client, **ESTIMATE).json()["chargers"][1]["est_soc"]

    at = post(client, **ESTIMATE, reserve_soc=est_b).json()["chargers"][1]
    above = post(client, **ESTIMATE, reserve_soc=est_b + 0.1).json()["chargers"][1]

    assert at["reachable"] is True
    assert above["reachable"] is False


def test_need_charge_speech_recommends_the_first_reachable_charger(client, stations):
    body = post(client, **ESTIMATE).json()

    first = body["chargers"][0]
    assert first["distance_m"] == pytest.approx(
        first["along_m"] * 60_000 / body["route_m"] + first["offset_m"], abs=1
    )
    distance = spoken_distance(first["distance_m"])
    assert body["speech"] == (
        f"이대로면 도착할 때 배터리가 8%예요. {distance} 앞, 경로에서 약 1킬로미터 벗어난 "
        "A 충전소에 비어 있는 급속충전기가 1대 있어요. 경유지로 넣을까요?"
    )
    assert body["actions"] == [
        {
            "type": "add_waypoint",
            "station_id": "A",
            "name": "A 충전소",
            "lat": 35.09,
            "lng": 126.8 + KM_EAST,
        }
    ]


def test_skips_unreachable_chargers_for_the_recommendation(client, stations):
    est_a = post(client, **ESTIMATE).json()["chargers"][0]["est_soc"]
    est_b = post(client, **ESTIMATE).json()["chargers"][1]["est_soc"]

    # 둘 다 못 가면 가장 가까운 곳을 추천하고 내려갈 잔량을 말한다
    none_reachable = post(client, **ESTIMATE, reserve_soc=est_a + 1).json()

    assert none_reachable["actions"][0]["station_id"] == "A"
    assert f"가는 동안 배터리가 {est_a:g}%까지 내려갈 수 있어요." in none_reachable["speech"]
    assert est_b < est_a


def test_no_need_to_charge_still_returns_chargers(client, stations):
    body = post(client, arrival_soc=35, remain_distance_m=60_000).json()

    assert body["need_charge"] is False
    assert body["speech"] == "도착할 때 배터리가 35% 남아요. 충전 없이 가셔도 돼요."
    assert [c["station_id"] for c in body["chargers"]] == ["A", "B"]
    assert body["actions"] == []


@pytest.mark.parametrize("missing", [{"arrival_soc": 8}, {"remain_distance_m": 60_000}, {}])
def test_without_all_three_values_nothing_is_estimated(client, stations, missing):
    body = post(client, **missing).json()

    assert all(c["est_soc"] is None and c["reachable"] is None for c in body["chargers"])
    assert not any("추정했어요" in a for a in body["assumptions"])
    assert body["need_charge"] is (None if "arrival_soc" not in missing else True)


def test_without_arrival_soc_the_speech_only_offers_the_charger(client, stations):
    body = post(client).json()

    # 남은 거리가 없으면 도로 계수 1.25: 10km 앞 × 1.25 + 1km 옆
    assert body["chargers"][0]["distance_m"] == pytest.approx(13_500, rel=0.01)
    assert body["speech"] == (
        "약 13.5킬로미터 앞, 경로에서 약 1킬로미터 벗어난 A 충전소에 비어 있는 급속충전기가 "
        "1대 있어요. 경유지로 넣을까요?"
    )
    assert body["assumptions"][-1] == (
        "내비 남은 거리가 없어 도로 거리를 직선거리의 1.25배(도로 계수)로 잡았어요."
    )


def test_need_charge_but_nothing_free_says_so_and_explains(client, db_session):
    station(db_session, "BUSY", 35.2, chargers=[charger(status="3")])

    body = post(client, **ESTIMATE).json()

    assert body["chargers"] == [] and body["actions"] == []
    assert body["speech"] == (
        "이대로면 도착할 때 배터리가 8%예요. 경로 근처에 지금 비어 있는 급속충전기를 찾지 못했어요."
    )
    assert body["coverage_note"] == (
        "경로 근처 충전소 1곳 중 지금 비어 있는 50kW 이상 충전기가 없어요."
    )


def test_no_station_near_the_route_is_a_coverage_note(client, db_session):
    station(db_session, "SEOUL", 37.5, 127.0)

    body = post(client).json()

    assert body["chargers"] == []
    assert body["coverage_note"] == "이 구간은 충전소 정보가 없을 수 있어요(수집 지역 밖)."
    assert body["speech"] == "경로 근처에 지금 비어 있는 급속충전기를 찾지 못했어요."


def test_empty_cache_is_503(client):
    response = post(client)

    assert response.status_code == 503


def test_slow_min_kw_says_charger(client, db_session):
    station(db_session, "S", 35.2, chargers=[charger(kw=7.0)])

    body = post(client, min_kw=7).json()

    assert "비어 있는 충전기가 1대 있어요" in body["speech"]


def test_station_names_are_cut_to_40_chars(client, db_session):
    station(db_session, "LONG", 35.2, name="가" * 30 + "\n" + "나" * 30)

    item = post(client).json()["chargers"][0]

    assert len(item["name"]) == 40
    assert "\n" not in item["name"]


@pytest.mark.parametrize(
    "body",
    [
        {"route_points": [{"lat": 35.1, "lng": 126.8}] * 51},
        {"corridor_m": 499},
        {"corridor_m": 10_001},
        {"min_kw": 0},
        {"soc_now": 101},
        {"reserve_soc": -1},
        {"remain_distance_m": 0},
        {"origin": {"lat": 86, "lng": 126.8}},
        {"origin": {"lat": 35.0, "lng": 181}},
        # 날짜변경선을 건너는 선분
        {"origin": {"lat": 50.0, "lng": 179.9}, "destination": {"lat": 50.0, "lng": -179.9}},
        # 1,000km 넘는 경로
        {"destination": {"lat": 45.0, "lng": 126.8}},
    ],
)
def test_bad_requests_are_422(client, body):
    payload = {"origin": ORIGIN, "destination": DEST, "soc_now": 60, **body}

    response = client.post(URL, json=payload)

    assert response.status_code == 422


def test_fifty_route_points_are_accepted(client, stations):
    points = [{"lat": 35.0 + i * 0.01, "lng": 126.8} for i in range(1, 51)]

    assert post(client, route_points=points).status_code == 200


def test_far_east_and_west_longitudes_do_not_break(client, db_session):
    station(db_session, "E", 50.0, 179.95)
    body = post(
        client, origin={"lat": 50.0, "lng": 179.9}, destination={"lat": 50.0, "lng": 179.99}
    ).json()

    assert [c["station_id"] for c in body["chargers"]] == ["E"]


# 뒤 충전소 판정: 앱이 지나온 경로 지점이나 현재 위치에 붙은 지점을 보내도 남은 경로만 쓴다.
PASSED_POINTS = {
    "same_as_origin": [ORIGIN],
    "3m_beside": [{"lat": 35.0, "lng": 126.8 + 0.000033}],
    "50m_behind": [{"lat": 35.0 - 0.00045, "lng": 126.8}],
    # 출발할 때의 경로 시작점(11km 뒤)이 그대로 남아 있음
    "trip_start_11km_behind": [{"lat": 34.9, "lng": 126.8}],
}


@pytest.mark.parametrize("points", PASSED_POINTS.values(), ids=PASSED_POINTS.keys())
def test_passed_route_points_do_not_bring_back_stations_behind(client, stations, points):
    baseline = post(client, **ESTIMATE).json()

    body = post(client, **ESTIMATE, route_points=points).json()

    assert "BEHIND" not in [c["station_id"] for c in body["chargers"]]
    assert body == baseline
    assert body["actions"][0]["station_id"] == "A"


def test_passed_points_before_a_bend_are_dropped_but_the_bend_stays(client, db_session):
    # 지나온 지점(뒤 5km) → 현재 위치 → 동쪽으로 꺾는 지점 → 목적지
    station(db_session, "EAST", 35.25, 126.9)
    bend = {"lat": 35.25, "lng": 126.9}

    with_passed = post(client, route_points=[{"lat": 34.955, "lng": 126.8}, bend]).json()
    without = post(client, route_points=[bend]).json()

    assert with_passed == without
    assert [c["station_id"] for c in with_passed["chargers"]] == ["EAST"]


def test_long_route_without_route_points_is_searched(client, db_session):
    # 155km 북쪽, 경유지 없음(NaviHelper는 경로 모양 점을 주지 않는다)
    station(db_session, "FAR", 36.2, 126.8 + KM_EAST)
    body = client.post(
        URL,
        json={"origin": ORIGIN, "destination": {"lat": 36.4, "lng": 126.8}, "soc_now": 60},
    )

    assert body.status_code == 200
    result = body.json()
    assert result["route_m"] == pytest.approx(155_673, rel=0.001)
    assert [c["station_id"] for c in result["chargers"]] == ["FAR"]
    assert result["chargers"][0]["offset_m"] == pytest.approx(1_000, rel=0.02)
    assert "도로 옆 휴게소가 검색 범위 밖일 수 있어요" in result["assumptions"][2]


def test_short_segments_have_no_long_route_assumption(client, stations):
    assumptions = post(client).json()["assumptions"]

    assert not any("검색 범위 밖" in a for a in assumptions)


def test_argus_input_is_bounded_by_query_boxes_and_row_cap(client, db_session, monkeypatch):
    # 수집 지역 대각선 + 출발지와 같은 경로 점 50개, corridor 10km
    origin = {"lat": 34.2, "lng": 126.0}
    station(db_session, "MID", 34.8, 126.85)
    seen = {}
    real = car_route_service.rows_in_boxes

    def spy(session, boxes, *, limit=None):
        seen["boxes"], seen["limit"] = len(boxes), limit
        return real(session, boxes, limit=limit)

    monkeypatch.setattr(car_route_service, "rows_in_boxes", spy)
    response = client.post(
        URL,
        json={
            "origin": origin,
            "destination": {"lat": 35.4, "lng": 127.7},
            "route_points": [origin] * 50,
            "soc_now": 60,
            "corridor_m": 10_000,
        },
    )

    assert response.status_code == 200
    body = response.json()
    # 같은 점 50개는 합쳐져 선분 하나(약 205km)가 되고, 10km 조각 21개로 찾는다
    assert body["route_m"] == pytest.approx(205_000, rel=0.01)
    assert seen == {"boxes": 21, "limit": car_route_service.MAX_CANDIDATE_ROWS + 1}
    assert [c["station_id"] for c in body["chargers"]] == ["MID"]


def test_candidate_rows_are_capped_in_route_order(client, db_session, monkeypatch):
    for index in range(4):
        station(db_session, f"S{index}", 35.4 - index * 0.1)  # S3가 가장 앞
    monkeypatch.setattr(car_route_service, "MAX_CANDIDATE_ROWS", 3)

    body = post(client).json()

    assert [c["station_id"] for c in body["chargers"]] == ["S3", "S2", "S1"]
    assert body["coverage_note"] == "경로 근처 충전소가 많아 앞쪽 구간의 충전소만 살펴봤어요."


def test_candidate_cap_note_is_added_to_the_no_match_note(client, db_session, monkeypatch):
    for index in range(3):
        station(db_session, f"BUSY{index}", 35.1 + index * 0.1, chargers=[charger(status="3")])
    monkeypatch.setattr(car_route_service, "MAX_CANDIDATE_ROWS", 2)

    body = post(client).json()

    assert body["coverage_note"] == (
        "경로 근처 충전소 2곳 중 지금 비어 있는 50kW 이상 충전기가 없어요. "
        "경로 근처 충전소가 많아 앞쪽 구간의 충전소만 살펴봤어요."
    )


def test_station_next_to_the_start_is_not_spoken_as_10m_ahead(client, db_session):
    # 현재 위치 바로 옆(동쪽 2.5km), 경로 진행 방향으로는 거의 0m
    station(db_session, "SIDE", 35.0005, 126.8 + 2.5 * KM_EAST)

    body = post(client).json()

    item = body["chargers"][0]
    assert item["along_m"] < 100
    assert item["distance_m"] == pytest.approx(item["along_m"] * 1.25 + item["offset_m"], abs=1)
    assert item["offset_m"] == pytest.approx(2_500, rel=0.01)
    assert body["speech"].startswith(
        f"{spoken_distance(item['distance_m'])} 앞, 경로에서 약 2.5킬로미터 벗어난 SIDE 충전소에"
    )


@pytest.mark.parametrize(
    ("meters", "spoken"),
    [
        (3, "약 10미터"),
        (994, "약 990미터"),
        (995, "약 1킬로미터"),
        (1049, "약 1킬로미터"),
        (1050, "약 1.1킬로미터"),
        (22_239, "약 22.2킬로미터"),
    ],
)
def test_spoken_distance_picks_the_unit_after_rounding(meters, spoken):
    assert spoken_distance(meters) == spoken


def test_station_close_to_the_route_does_not_mention_the_offset(client, db_session):
    station(db_session, "ON", 35.2, 126.8 + 0.4 * KM_EAST)  # 400m 옆

    body = post(client).json()

    item = body["chargers"][0]
    assert "벗어난" not in body["speech"]
    assert body["speech"].startswith(f"{spoken_distance(item['distance_m'])} 앞 ON 충전소에")


EFFICIENCY = {"efficiency_km_per_kwh": 5.0, "battery_capacity_wh": 77_400}


def test_estimates_from_efficiency_when_navigation_values_are_missing(client, stations):
    body = post(client, **EFFICIENCY).json()

    rate = 100 / (5.0 * 77_400)  # %/m
    for item in body["chargers"]:
        assert item["distance_m"] == pytest.approx(
            item["along_m"] * 1.25 + item["offset_m"], abs=1
        )
        assert item["est_soc"] == pytest.approx(60 - rate * item["distance_m"], abs=0.1)
        assert item["reachable"] is True
    assert body["assumptions"][-2:] == [
        "내비 남은 거리가 없어 도로 거리를 직선거리의 1.25배(도로 계수)로 잡았어요.",
        "충전소 도착 잔량은 최근 전비와 배터리 용량으로 거리에 비례해 추정했어요.",
    ]
    # 목적지 도착 잔량도 전비로 추정한다: 꺾은선 × 1.25
    arrival = round(60 - rate * body["route_m"] * 1.25, 1)
    assert body["need_charge"] is False
    assert body["speech"] == (
        f"전비로 추정하면 도착할 때 배터리가 {arrival:g}% 남아요. 충전 없이 가셔도 돼요."
    )
    assert body["actions"] == []


def test_efficiency_estimate_can_say_a_charge_is_needed(client, stations):
    body = post(client, **EFFICIENCY, soc_now=25).json()

    rate = 100 / (5.0 * 77_400)
    arrival = round(25 - rate * body["route_m"] * 1.25, 1)
    assert arrival < 15
    assert body["need_charge"] is True
    assert body["speech"].startswith(f"전비로 추정하면 도착할 때 배터리가 {arrival:g}%예요. ")
    assert body["speech"].endswith("경유지로 넣을까요?")
    assert body["actions"][0]["station_id"] == "A"


def test_navigation_arrival_is_not_called_an_efficiency_estimate(client, stations):
    body = post(client, **EFFICIENCY, arrival_soc=8).json()

    # 남은 거리가 없어 소모율은 전비로 구하지만, 도착 잔량은 내비 값 그대로
    assert body["need_charge"] is True
    assert body["speech"].startswith("이대로면 도착할 때 배터리가 8%예요. ")


def test_navigation_estimate_wins_over_efficiency(client, stations):
    both = post(client, **ESTIMATE, **EFFICIENCY).json()
    navi = post(client, **ESTIMATE).json()

    assert both["chargers"] == navi["chargers"]
    assert both["assumptions"] == navi["assumptions"]


def test_efficiency_with_remaining_distance_uses_the_road_scale(client, stations):
    # arrival_soc 없이 남은 거리만: 전비로 추정하되 거리는 도로 비율로 늘린다
    body = post(client, **EFFICIENCY, remain_distance_m=60_000).json()

    item = body["chargers"][0]
    scale = 60_000 / body["route_m"]
    assert item["distance_m"] == pytest.approx(
        item["along_m"] * scale + item["offset_m"], abs=1
    )
    assert item["est_soc"] == pytest.approx(
        60 - 100 / (5.0 * 77_400) * item["distance_m"], abs=0.1
    )


@pytest.mark.parametrize(
    "partial", [{"efficiency_km_per_kwh": 5.0}, {"battery_capacity_wh": 77_400}]
)
def test_efficiency_needs_capacity_too(client, stations, partial):
    body = post(client, **partial).json()

    assert all(c["est_soc"] is None for c in body["chargers"])
    assert body["need_charge"] is None
    assert not any("추정했어요" in a for a in body["assumptions"])


@pytest.mark.parametrize(
    "bad",
    [
        {"efficiency_km_per_kwh": 0},
        {"efficiency_km_per_kwh": 20.1},
        {"battery_capacity_wh": 999},
    ],
)
def test_efficiency_bounds(client, bad):
    assert post(client, **bad).status_code == 422


# Momus 재현: 경유지 없는 155km, 잔량 25%, 전비 5km/kWh, 77.4kWh → 주행 가능 약 96.75km
LONG_DEST = {"lat": 36.4, "lng": 126.8}
LOW = {**EFFICIENCY, "soc_now": 25}
RANGE_M = 25 / (100 / (5.0 * 77_400))


def post_long(client, **body):
    return client.post(URL, json={"origin": ORIGIN, "destination": LONG_DEST, **LOW, **body})


def test_station_beyond_range_is_not_spoken_as_reaching_zero(client, db_session):
    # 경로 77.84km 앞, 2km 옆 → 도로 거리 약 99.3km
    station(db_session, "MID", 35.7, 126.8 + 2 * KM_EAST)

    body = post_long(client).json()

    item = body["chargers"][0]
    assert item["distance_m"] == pytest.approx(99_300, rel=0.01) and item["distance_m"] > RANGE_M
    assert (item["est_soc"], item["reachable"], item["runs_out"]) == (0, False, True)
    assert "0%" not in body["speech"]
    assert body["speech"] == (
        "전비로 추정하면 목적지에 닿기 전에 배터리가 바닥날 수 있어요. "
        f"{spoken_distance(item['distance_m'])} 앞, 경로에서 약 2킬로미터 벗어난 MID 충전소에 "
        "비어 있는 급속충전기가 1대 있어요. 이 충전소까지 가기 전에 배터리가 바닥날 수 있어요. "
        "더 가까운 충전소를 찾아볼까요?"
    )
    assert body["actions"] == [{"type": "ask", "question": "더 가까운 충전소를 찾아볼까요?"}]


def test_a_nearer_reachable_station_is_recommended_instead(client, db_session):
    station(db_session, "MID", 35.7, 126.8 + 2 * KM_EAST)
    station(db_session, "NEAR", 35.18)  # 20km 앞 → 도로 25km, 약 18.5% 남음

    body = post_long(client).json()

    assert [c["station_id"] for c in body["chargers"]] == ["NEAR", "MID"]
    assert [c["runs_out"] for c in body["chargers"]] == [False, True]
    assert body["actions"][0] == {
        "type": "add_waypoint", "station_id": "NEAR", "name": "NEAR 충전소", "lat": 35.18,
        "lng": 126.8,
    }
    assert body["speech"].endswith("경유지로 넣을까요?")


def test_a_later_station_that_does_not_run_out_wins_over_an_earlier_one_that_does(
    client, db_session
):
    # FAR_SIDE: 76km 앞, 2.9km 옆 → 도로 97.9km (바닥남)
    # ON_ROUTE: 76.5km 앞, 0.1km 옆 → 도로 95.7km (바닥나지 않지만 기준 15% 아래)
    station(db_session, "FAR_SIDE", 35.0 + 76 / 111.195, 126.8 + 2.9 * KM_EAST)
    station(db_session, "ON_ROUTE", 35.0 + 76.5 / 111.195, 126.8 + 0.1 * KM_EAST)

    body = post_long(client).json()

    assert [c["station_id"] for c in body["chargers"]] == ["FAR_SIDE", "ON_ROUTE"]
    assert [c["runs_out"] for c in body["chargers"]] == [True, False]
    assert body["actions"][0]["station_id"] == "ON_ROUTE"
    low = body["chargers"][1]["est_soc"]
    assert 0 < low < 15
    assert f"가는 동안 배터리가 {low:g}%까지 내려갈 수 있어요. 경유지로 넣을까요?" in body["speech"]


def test_runs_out_is_null_without_an_estimate_and_false_when_fine(client, stations):
    without = post(client).json()
    navi = post(client, **ESTIMATE).json()

    assert all(c["runs_out"] is None for c in without["chargers"])
    assert all(c["runs_out"] is False for c in navi["chargers"])


# ── 상태 신선도 (BE-10) ───────────────────────────────────────────────────

FRESH_NOW = datetime(2026, 11, 16, 18, 0, tzinfo=KST)
NEED = {"arrival_soc": 8, "remain_distance_m": 60_000}


def aged(db_session, station_id, lat, age_min, *, chargers=None):
    station(db_session, station_id, lat, chargers=chargers)
    db_session.execute(
        update(ChargerCache)
        .where(ChargerCache.station_id == station_id)
        .values(updated_at=FRESH_NOW - timedelta(minutes=age_min))
    )


@pytest.fixture
def fixed_now(monkeypatch):
    monkeypatch.setattr(car, "now_kst", lambda: FRESH_NOW)


def test_route_chargers_carry_status_age(client, db_session, fixed_now):
    aged(db_session, "A", 35.09, 15)

    found = post(client).json()["chargers"][0]

    assert found["synced_at"] == "2026-11-16T17:45:00+09:00"
    assert (found["status_age_min"], found["stale"]) == (15, False)


@pytest.mark.parametrize(("age", "suffix"), [(20, False), (21, True), (60, True)])
def test_stale_recommendation_says_how_old_the_status_is(
    client, db_session, fixed_now, age, suffix
):
    aged(db_session, "A", 35.09, age)

    speech = post(client, **NEED).json()["speech"]

    sentence = f"충전기 상태는 {age}분 전 정보예요."
    assert (sentence in speech) is suffix
    assert speech.endswith("경유지로 넣을까요?")
    if suffix:
        assert f"대 있어요. {sentence} 경유지로 넣을까요?" in speech


def test_status_older_than_an_hour_is_not_recommended(client, db_session, fixed_now):
    aged(db_session, "OLD", 35.05, 61)
    aged(db_session, "NEW", 35.2, 5)

    body = post(client, **NEED).json()

    assert [c["station_id"] for c in body["chargers"]] == ["NEW"]
    assert body["coverage_note"] is None


def test_empty_only_because_of_old_status_says_so(client, db_session, fixed_now):
    from evcharge.api.routes.chargers import STATUS_UNKNOWN_NOTE

    aged(db_session, "OLD", 35.05, 61)
    aged(db_session, "BUSY", 35.06, 0, chargers=[charger(status="3")])

    body = post(client, **NEED).json()

    assert body["chargers"] == []
    assert body["coverage_note"] == STATUS_UNKNOWN_NOTE
    assert body["speech"] == f"이대로면 도착할 때 배터리가 8%예요. {STATUS_UNKNOWN_NOTE}"
    assert body["actions"] == []


def test_empty_for_other_reasons_keeps_the_old_note(client, db_session, fixed_now):
    aged(db_session, "BUSY", 35.06, 90, chargers=[charger(status="3")])

    body = post(client, **NEED).json()

    assert body["coverage_note"] == (
        "경로 근처 충전소 1곳 중 지금 비어 있는 50kW 이상 충전기가 없어요."
    )
    assert body["speech"].endswith("경로 근처에 지금 비어 있는 급속충전기를 찾지 못했어요.")
