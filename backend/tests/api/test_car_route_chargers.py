"""``POST /api/car/chargers/along-route`` (BE-7)."""

from __future__ import annotations

import pytest

from evcharge.api.car_plan_service import spoken_distance
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
    distance = spoken_distance(first["along_m"] * 60_000 / body["route_m"])
    assert body["speech"] == (
        f"이대로면 도착할 때 배터리가 8%예요. {distance} 앞 A 충전소에 "
        "비어 있는 급속충전기가 1대 있어요. 경유지로 넣을까요?"
    )
    assert body["actions"] == [
        {"type": "add_waypoint", "station_id": "A", "name": "A 충전소", "lat": 35.09,
         "lng": 126.8 + KM_EAST}
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


@pytest.mark.parametrize(
    "missing", [{"arrival_soc": 8}, {"remain_distance_m": 60_000}, {}]
)
def test_without_all_three_values_nothing_is_estimated(client, stations, missing):
    body = post(client, **missing).json()

    assert all(c["est_soc"] is None and c["reachable"] is None for c in body["chargers"])
    assert len(body["assumptions"]) == 2


def test_without_arrival_soc_the_speech_only_offers_the_charger(client, stations):
    body = post(client).json()

    assert body["speech"].startswith("약 10")
    assert body["speech"].endswith(
        "앞 A 충전소에 비어 있는 급속충전기가 1대 있어요. 경유지로 넣을까요?"
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
