"""F-07 주변 충전소 조회.

라우터는 **캐시만 읽는다** — 공공 API를 부르지 않는다(하루 1,000건 한도).
그래서 이 테스트도 네트워크를 타지 않고, 캐시 행을 직접 심어 검증한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from evcharge.api.auth_deps import SESSION_COOKIE
from evcharge.api.routes.chargers import charger_api_key, charger_summary, find_nearby
from evcharge.domain.pricing import KST
from evcharge.infra.models import ChargerCache, FavoriteStation, User
from evcharge.infra.models import Session as SessionModel
from evcharge.infra.security import hash_password, hash_token, new_session_token

# 나주 빛가람동. 대회 지역 좌표로 검증한다.
HERE = (35.0175, 126.7905)

# 위도 0.009도 ≈ 1,001m, 0.027도 ≈ 3,002m
NEAR = (HERE[0] + 0.009, HERE[1])
FAR = (HERE[0] + 0.027, HERE[1])


@pytest.fixture(autouse=True)
def _api_key_configured(client):
    """키가 설정된 상태를 기본으로 둔다.

    라우터는 캐시만 읽지만 "키가 없으면 501"이라는 분기가 있어서(settings.py),
    개발자 ``.env``에 키가 있느냐에 따라 테스트 결과가 달라지면 안 된다.
    """
    client.app.dependency_overrides[charger_api_key] = lambda: "test-key"
    return client


def _charger(charger_id="01", charger_type="06", status="2", capacity_kw=50.0):
    return {
        "charger_id": charger_id,
        "type": charger_type,
        "capacity_kw": capacity_kw,
        "status": status,
        "status_updated_at": "2026-09-21T21:29:33+09:00",
    }


def _cache(db_session, station_id, coords, *, name="충전소", chargers=None, **overrides):
    lat, lng = coords
    data = {
        "name": name,
        "address": "전남광주통합특별시 나주시 빛가람로 1",
        "lat": lat,
        "lng": lng,
        "operator": "기후에너지환경부",
        "available_hours": "24시간 이용가능",
        "chargers": chargers if chargers is not None else [_charger()],
    }
    data.update(overrides)
    db_session.add(ChargerCache(station_id=station_id, data=data, lat=lat, lng=lng))
    db_session.commit()


def _login(client, db_session) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email="stations@example.com",
        password_hash=hash_password("password123"),
        nickname="테스터",
    )
    db_session.add(user)
    # 세션 행의 FK가 users를 가리키므로 사용자를 먼저 확정한다.
    db_session.commit()
    token = new_session_token()
    db_session.add(
        SessionModel(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(KST) + timedelta(days=14),
        )
    )
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, token)
    return user


def _get(client, **params):
    query = {"lat": HERE[0], "lng": HERE[1], **params}
    return client.get("/api/chargers", params=query)


# ---------------------------------------------------------------------------
# 입력 검증
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("params", [{}, {"lat": 35.0}, {"lng": 126.7}])
def test_missing_coordinates_is_422(client, params):
    assert client.get("/api/chargers", params=params).status_code == 422


def test_coordinates_outside_the_globe_are_422(client):
    assert client.get("/api/chargers", params={"lat": 91, "lng": 126.7}).status_code == 422
    assert client.get("/api/chargers", params={"lat": 35.0, "lng": 200}).status_code == 422


def test_absurd_radius_is_422(client):
    # 인증 없이 닿는 경로라 상한을 둔다(I-4와 같은 이유). 지구 전체를 훑게 하면
    # 캐시 3만 건을 파이썬으로 끌어오게 된다.
    assert _get(client, radius_m=10_000_000).status_code == 422
    assert _get(client, radius_m=0).status_code == 422


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------


def test_returns_cached_stations_within_the_radius(client, db_session):
    _cache(db_session, "ST-HERE", HERE, name="빛가람 충전소")

    response = _get(client)

    assert response.status_code == 200
    (station,) = response.json()
    assert station["station_id"] == "ST-HERE"
    assert station["name"] == "빛가람 충전소"
    assert station["operator"] == "기후에너지환경부"
    assert station["available_hours"] == "24시간 이용가능"
    assert station["distance_m"] == 0
    assert isinstance(station["distance_m"], int)


def test_stations_outside_the_radius_are_dropped(client, db_session):
    _cache(db_session, "ST-NEAR", NEAR)
    _cache(db_session, "ST-FAR", FAR)

    body = _get(client).json()

    # 기본 반경 2,000m. 3km 밖은 빠진다.
    assert [item["station_id"] for item in body] == ["ST-NEAR"]


def test_a_wider_radius_brings_the_far_one_back(client, db_session):
    _cache(db_session, "ST-NEAR", NEAR)
    _cache(db_session, "ST-FAR", FAR)

    body = _get(client, radius_m=5000).json()

    assert [item["station_id"] for item in body] == ["ST-NEAR", "ST-FAR"]


def test_the_bounding_box_corner_is_not_inside_the_circle(client, db_session):
    """박스로 좁힌 뒤 정확한 거리로 한 번 더 거르는지.

    북쪽 1,500m·동쪽 1,500m는 바운딩 박스 안이지만 실제 거리는 약 2,121m라
    반경 2,000m 밖이다. 박스만 믿으면 이 행이 섞여 들어온다.
    """
    _cache(db_session, "ST-CORNER", (HERE[0] + 0.0135, HERE[1] + 0.0165))

    assert _get(client).json() == []


def test_results_are_sorted_by_distance(client, db_session):
    _cache(db_session, "ST-FAR", FAR)
    _cache(db_session, "ST-HERE", HERE)
    _cache(db_session, "ST-NEAR", NEAR)

    body = _get(client, radius_m=5000).json()

    assert [item["station_id"] for item in body] == ["ST-HERE", "ST-NEAR", "ST-FAR"]
    assert [item["distance_m"] for item in body] == sorted(item["distance_m"] for item in body)


def test_distance_is_measured_from_the_given_point(client, db_session):
    _cache(db_session, "ST-NEAR", NEAR)

    (station,) = _get(client).json()

    # 위도 0.009도 ≈ 1,001m
    assert 995 <= station["distance_m"] <= 1005


def test_every_charger_of_a_station_comes_back_together(client, db_session):
    _cache(
        db_session,
        "ST-MULTI",
        HERE,
        chargers=[_charger("01"), _charger("02", status="3"), _charger("03")],
    )

    (station,) = _get(client).json()

    assert [charger["charger_id"] for charger in station["chargers"]] == ["01", "02", "03"]
    assert station["chargers"][1]["status"] == "3"


def test_unknown_status_code_is_returned_verbatim(client, db_session):
    """실제 데이터의 11.9%가 문서에 없는 `9`다. 백엔드가 추정 매핑을 넣으면
    '사용 가능'이라 적힌 자리에 사용자가 헛걸음한다."""
    _cache(db_session, "ST-UNKNOWN", HERE, chargers=[_charger(status="9")])

    (station,) = _get(client).json()

    assert station["chargers"][0]["status"] == "9"


def test_stations_without_coordinates_never_surface(client, db_session):
    # F-14가 만든 좌표 없는 캐시 행(즐겨찾기만 있고 아직 수집 전)도 섞이면 안 된다.
    db_session.add(ChargerCache(station_id="ST-NOCOORD", data={"name": "좌표 없음"}))
    db_session.commit()
    _cache(db_session, "ST-HERE", HERE)

    assert [item["station_id"] for item in _get(client).json()] == ["ST-HERE"]


# ---------------------------------------------------------------------------
# charger_type 필터
# ---------------------------------------------------------------------------


def test_charger_type_filter_keeps_only_matching_stations(client, db_session):
    _cache(db_session, "ST-DC", HERE, chargers=[_charger("01", charger_type="06")])
    _cache(db_session, "ST-AC", NEAR, chargers=[_charger("01", charger_type="02")])

    body = _get(client, charger_type="02").json()

    assert [item["station_id"] for item in body] == ["ST-AC"]


def test_charger_type_filter_matches_any_charger_of_the_station(client, db_session):
    _cache(
        db_session,
        "ST-MIXED",
        HERE,
        chargers=[_charger("01", charger_type="06"), _charger("02", charger_type="02")],
    )

    (station,) = _get(client, charger_type="02").json()

    # 걸러낸 것은 충전소이지 충전기가 아니다 — 화면은 그 충전소의 충전기를 다 보여준다.
    assert len(station["chargers"]) == 2


def test_charger_type_filter_ignores_case_and_padding(client, db_session):
    _cache(db_session, "ST-DC", HERE, chargers=[_charger("01", charger_type="DC")])

    assert len(_get(client, charger_type=" dc ").json()) == 1


# ---------------------------------------------------------------------------
# is_favorite (명세 2-4)
# ---------------------------------------------------------------------------


def test_is_favorite_is_null_for_a_guest(client, db_session):
    _cache(db_session, "ST-HERE", HERE)

    (station,) = _get(client).json()

    # false가 아니라 null이다 — 게스트에게는 "즐겨찾기 안 함"이 아니라
    # "즐겨찾기라는 개념이 아직 없음"이다.
    assert station["is_favorite"] is None


def test_is_favorite_is_true_or_false_when_logged_in(client, db_session):
    user = _login(client, db_session)
    _cache(db_session, "ST-HERE", HERE)
    _cache(db_session, "ST-NEAR", NEAR)
    db_session.add(FavoriteStation(user_id=user.id, station_id="ST-HERE"))
    db_session.commit()

    body = {item["station_id"]: item["is_favorite"] for item in _get(client).json()}

    assert body == {"ST-HERE": True, "ST-NEAR": False}


def test_another_users_favorite_does_not_leak(client, db_session):
    _login(client, db_session)
    other = User(
        id=str(uuid.uuid4()),
        email="other@example.com",
        password_hash=hash_password("password123"),
        nickname="남",
    )
    db_session.add(other)
    _cache(db_session, "ST-HERE", HERE)
    db_session.add(FavoriteStation(user_id=other.id, station_id="ST-HERE"))
    db_session.commit()

    (station,) = _get(client).json()

    assert station["is_favorite"] is False


# ---------------------------------------------------------------------------
# 데이터가 아직 없을 때
# ---------------------------------------------------------------------------


def test_no_api_key_still_answers_501(client):
    """키가 없으면 캐시를 채울 방법 자체가 없다. settings.py가 약속한 대로
    501을 유지한다 — 프론트가 "아직 열리지 않았어요"로 안내하고 있다."""
    client.app.dependency_overrides[charger_api_key] = lambda: ""

    response = _get(client)

    assert response.status_code == 501
    assert isinstance(response.json()["detail"], str)


def test_empty_cache_is_503_not_an_empty_list(client, db_session):
    """캐시가 통째로 비어 있으면 "주변에 충전소가 없다"가 아니라 "아직 수집하지
    않았다"이다. 200 []로 답하면 화면이 나주에 충전소가 없다고 말하게 된다."""
    response = _get(client)

    assert response.status_code == 503
    assert "수집" in response.json()["detail"]


def test_a_filled_cache_with_nothing_nearby_is_an_empty_list(client, db_session):
    _cache(db_session, "ST-FAR", FAR)

    response = _get(client)

    assert response.status_code == 200
    assert response.json() == []


def test_the_cache_the_sync_writes_fills_in_the_favorites_screen(client, db_session):
    """F-14가 이 캐시를 읽는다 (routes/me_favorites.py).

    수집기가 쓰는 ``data`` 모양이 어긋나면 즐겨찾기 화면이 조용히 station_id만
    남은 채로 돌아간다 — 그쪽 테스트는 자기 손으로 심은 캐시를 보기 때문에
    이 어긋남을 못 잡는다. 두 쪽을 실제로 이어 붙여 확인한다.
    """
    from evcharge.infra.charger_sync import sync_stations

    class _Api:
        def fetch_station_rows(self, zcode):
            return [
                {
                    "statId": "ME174085",
                    "statNm": "압해읍사무소",
                    "chgerId": "01",
                    "chgerType": "06",
                    "addr": "전남광주통합특별시 신안군 압해읍 학교리 585",
                    "lat": str(HERE[0]),
                    "lng": str(HERE[1]),
                    "useTime": "24시간 이용가능",
                    "busiNm": "기후에너지환경부",
                    "stat": "2",
                    "statUpdDt": "20260921212933",
                    "output": "50",
                }
            ]

        def fetch_status_rows(self, zcode, period):
            return []

    _login(client, db_session)
    sync_stations(db_session, _Api(), ["12"])
    assert client.put("/api/me/favorites/ME174085").status_code == 204

    (favorite,) = client.get("/api/me/favorites").json()

    assert favorite["name"] == "압해읍사무소"
    assert favorite["address"].startswith("전남광주통합특별시")
    assert favorite["lat"] == HERE[0]
    assert favorite["operator"] == "기후에너지환경부"
    assert favorite["available_hours"] == "24시간 이용가능"
    assert favorite["chargers"][0]["status"] == "2"
    # 거리는 요청 좌표가 있어야 나오는 값이라 캐시에 넣지 않는다 — 즐겨찾기
    # 화면은 위치를 묻지 않으므로 null이 맞다.
    assert favorite["distance_m"] is None


# ---------------------------------------------------------------------------
# available_only · min_kw 필터 (와트잇 BE-2 "충전 실패 피하기")
# ---------------------------------------------------------------------------


def _ids(response) -> list[str]:
    assert response.status_code == 200
    return [station["station_id"] for station in response.json()]


def _seed_mixed(db_session) -> None:
    """빈 충전기·출력이 서로 다른 충전소들. 가까운 순서는 이 순서다."""
    _cache(db_session, "ST-FREE-SLOW", HERE, chargers=[_charger("01", status="2", capacity_kw=7)])
    _cache(
        db_session,
        "ST-SPLIT",
        (HERE[0] + 0.002, HERE[1]),
        # 7kW는 비었고 100kW는 충전중이다.
        chargers=[
            _charger("01", status="2", capacity_kw=7),
            _charger("02", status="3", capacity_kw=100),
        ],
    )
    _cache(
        db_session,
        "ST-FREE-FAST",
        (HERE[0] + 0.004, HERE[1]),
        chargers=[_charger("01", status="2", capacity_kw=100)],
    )
    _cache(
        db_session,
        "ST-BUSY",
        (HERE[0] + 0.006, HERE[1]),
        chargers=[_charger("01", status="3", capacity_kw=50), _charger("02", status="5")],
    )
    _cache(db_session, "ST-EMPTY", NEAR, chargers=[])


def test_defaults_return_exactly_what_they_did_before(client, db_session):
    _seed_mixed(db_session)

    plain = _get(client)
    explicit = _get(client, available_only="false")

    assert _ids(plain) == ["ST-FREE-SLOW", "ST-SPLIT", "ST-FREE-FAST", "ST-BUSY", "ST-EMPTY"]
    assert explicit.json() == plain.json()


def test_available_only_keeps_stations_with_a_waiting_charger(client, db_session):
    _seed_mixed(db_session)

    response = _get(client, available_only="true")

    assert _ids(response) == ["ST-FREE-SLOW", "ST-SPLIT", "ST-FREE-FAST"]
    # 남긴 충전소의 충전기는 충전중인 것까지 전부 보인다. 상태 코드는 원문 그대로다.
    split = response.json()[1]
    assert [(c["charger_id"], c["status"]) for c in split["chargers"]] == [("01", "2"), ("02", "3")]


def test_min_kw_keeps_stations_with_a_charger_at_least_that_fast(client, db_session):
    _seed_mixed(db_session)

    assert _ids(_get(client, min_kw=50)) == ["ST-SPLIT", "ST-FREE-FAST", "ST-BUSY"]
    # 경계: 같은 출력이면 남긴다.
    assert _ids(_get(client, min_kw=100)) == ["ST-SPLIT", "ST-FREE-FAST"]
    assert _ids(_get(client, min_kw=100.5)) == []


def test_both_filters_must_hold_on_the_same_charger(client, db_session):
    _seed_mixed(db_session)

    # ST-SPLIT는 빈 7kW와 충전중인 100kW라, 각 조건만 따로 보면 남지만 같이 보면 빠진다.
    assert _ids(_get(client, available_only="true", min_kw=50)) == ["ST-FREE-FAST"]


def test_charger_type_joins_the_same_charger_rule(client, db_session):
    _cache(
        db_session,
        "ST-MIXED",
        HERE,
        # 02(AC완속)는 비었고 06은 충전중이다.
        chargers=[
            _charger("01", charger_type="02", status="2", capacity_kw=7),
            _charger("02", charger_type="06", status="3", capacity_kw=50),
        ],
    )

    # charger_type 하나만 주면 지금과 같다.
    assert _ids(_get(client, charger_type="06")) == ["ST-MIXED"]
    assert _ids(_get(client, charger_type="06", available_only="true")) == []
    assert _ids(_get(client, charger_type="02", available_only="true")) == ["ST-MIXED"]


def test_no_station_matching_with_a_filled_cache_is_an_empty_200(client, db_session):
    _seed_mixed(db_session)

    response = _get(client, available_only="true", min_kw=200)

    assert response.status_code == 200
    assert response.json() == []


def test_filters_on_an_empty_cache_still_say_it_is_not_collected(client):
    assert _get(client, available_only="true").status_code == 503


def test_unreadable_capacity_never_matches_min_kw(client, db_session):
    _cache(
        db_session,
        "ST-ODD",
        HERE,
        chargers=[
            _charger("01", capacity_kw=0.0),
            {**_charger("02"), "capacity_kw": "NaN"},
            {**_charger("03"), "capacity_kw": None},
        ],
    )
    _cache(db_session, "ST-OK", NEAR, chargers=[_charger("01", capacity_kw="50")])

    assert _ids(_get(client, min_kw=1)) == ["ST-OK"]


@pytest.mark.parametrize("min_kw", ["0", "-1", "1001", "nan", "inf", "-inf", "Infinity", "fast"])
def test_min_kw_out_of_range_is_422(client, min_kw):
    assert _get(client, min_kw=min_kw).status_code == 422


def test_available_only_must_be_a_boolean(client):
    assert _get(client, available_only="maybe").status_code == 422


# ── find_nearby / charger_summary: 음성 대화 도구가 직접 부르는 함수 ──────────


def test_find_nearby_matches_the_route_order_and_filters(client, db_session):
    _cache(db_session, "FAR", FAR, chargers=[_charger(status="2", capacity_kw=100.0)])
    _cache(db_session, "NEAR", NEAR, chargers=[_charger(status="3", capacity_kw=7.0)])
    _cache(db_session, "HERE", HERE, chargers=[_charger(status="2", capacity_kw=7.0)])

    every = find_nearby(db_session, lat=HERE[0], lng=HERE[1], radius_m=5_000)
    free_fast = find_nearby(
        db_session, lat=HERE[0], lng=HERE[1], radius_m=5_000, available_only=True, min_kw=50
    )
    route = _get(client, radius_m=5_000).json()

    assert [row.station_id for _, row in every] == ["HERE", "NEAR", "FAR"]
    assert [station["station_id"] for station in route] == ["HERE", "NEAR", "FAR"]
    assert [row.station_id for _, row in free_fast] == ["FAR"]
    assert round(every[1][0]) == route[1]["distance_m"]


def test_charger_summary_counts_free_chargers_and_top_output(db_session):
    _cache(
        db_session,
        "MIX",
        HERE,
        chargers=[
            _charger("01", status=" 2 ", capacity_kw=7.0),
            _charger("02", status="3", capacity_kw=100.0),
            _charger("03", status="2", capacity_kw="nan"),
        ],
    )
    row = db_session.get(ChargerCache, "MIX")

    assert charger_summary(row) == (2, 100.0)
