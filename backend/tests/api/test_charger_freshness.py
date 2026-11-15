"""충전기 상태 신선도 (BE-10): GET /api/chargers, GET /api/chargers/freshness."""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import unquote

import pytest

from evcharge.api.routes import chargers as chargers_route
from evcharge.api.routes.chargers import STATUS_UNKNOWN_NOTE, charger_api_key
from evcharge.domain.pricing import KST
from evcharge.infra.models import ChargerCache

NOW = datetime(2026, 11, 16, 18, 0, tzinfo=KST)
HERE = (35.0175, 126.7905)


@pytest.fixture(autouse=True)
def _setup(client, monkeypatch):
    client.app.dependency_overrides[charger_api_key] = lambda: "test-key"
    monkeypatch.setattr(chargers_route, "now_kst", lambda: NOW)


def station(db_session, station_id, age_min, *, status="2", lat_offset=0.0, lat=True):
    db_session.add(
        ChargerCache(
            station_id=station_id,
            data={
                "name": f"{station_id} 충전소",
                "chargers": [
                    {"charger_id": "01", "type": "06", "capacity_kw": 50.0, "status": status}
                ],
            },
            lat=HERE[0] + lat_offset if lat else None,
            lng=HERE[1] if lat else None,
            updated_at=NOW - timedelta(minutes=age_min),
        )
    )
    db_session.commit()


def get(client, **params):
    return client.get("/api/chargers", params={"lat": HERE[0], "lng": HERE[1], **params})


@pytest.mark.parametrize(
    ("age", "expected_age", "stale"),
    [
        (0, 0, False),
        (20, 20, False),
        (20.98, 20, False),  # 지난 분은 내림
        (21, 21, True),
        (60, 60, True),
        (-3, 0, False),  # 수집 시각이 서버 시계보다 뒤: 0
    ],
)
def test_each_station_carries_its_status_age(client, db_session, age, expected_age, stale):
    station(db_session, "A", age)

    body = get(client).json()

    assert body[0]["synced_at"] == (NOW - timedelta(minutes=age)).isoformat()
    assert (body[0]["status_age_min"], body[0]["stale"]) == (expected_age, stale)


def test_default_list_is_unchanged_apart_from_the_new_fields(client, db_session):
    station(db_session, "OLD", 600, status="2")

    body = get(client).json()

    assert [s["station_id"] for s in body] == ["OLD"]
    assert body[0]["chargers"][0]["status"] == "2"  # 상태값은 그대로 보여 준다
    assert body[0]["stale"] is True
    assert set(body[0]) == {
        "station_id",
        "name",
        "address",
        "lat",
        "lng",
        "distance_m",
        "operator",
        "available_hours",
        "is_favorite",
        "chargers",
        "synced_at",
        "status_age_min",
        "stale",
    }


@pytest.mark.parametrize(("age", "kept"), [(60, True), (61, False)])
def test_available_only_counts_status_up_to_60_minutes(client, db_session, age, kept):
    station(db_session, "A", age)

    response = get(client, available_only="true")

    assert [s["station_id"] for s in response.json()] == (["A"] if kept else [])


def test_empty_because_of_old_status_says_so_in_a_header(client, db_session):
    station(db_session, "OLD", 90)

    response = get(client, available_only="true")

    assert response.json() == []
    assert unquote(response.headers["X-Status-Note"]) == STATUS_UNKNOWN_NOTE


def test_no_note_when_nothing_would_match_anyway(client, db_session):
    station(db_session, "BUSY", 90, status="3")
    station(db_session, "FAR", 0, lat_offset=0.5)

    response = get(client, available_only="true")

    assert response.json() == []
    assert "X-Status-Note" not in response.headers


def test_no_note_when_fresh_stations_remain(client, db_session):
    station(db_session, "OLD", 90)
    station(db_session, "NEW", 5, lat_offset=0.001)

    response = get(client, available_only="true")

    assert [s["station_id"] for s in response.json()] == ["NEW"]
    assert "X-Status-Note" not in response.headers


def test_limits_are_settings(client, db_session, monkeypatch):
    monkeypatch.setenv("CHARGER_STATUS_STALE_MIN", "5")
    monkeypatch.setenv("CHARGER_STATUS_MAX_AGE_MIN", "10")
    station(db_session, "A", 11)

    assert get(client).json()[0]["stale"] is True
    assert get(client, available_only="true").json() == []


def test_freshness_summary(client, db_session):
    station(db_session, "A", 3)
    station(db_session, "B", 21, lat_offset=0.001)
    station(db_session, "C", 20, lat_offset=0.002)
    station(db_session, "NOCOORD", 500, lat=False)  # 즐겨찾기만 만든 행은 세지 않는다

    body = client.get("/api/chargers/freshness").json()

    assert body == {
        "latest_synced_at": (NOW - timedelta(minutes=3)).isoformat(),
        "oldest_synced_at": (NOW - timedelta(minutes=21)).isoformat(),
        "station_count": 3,
        "stale_count": 1,
    }


def test_freshness_of_an_empty_cache(client):
    assert client.get("/api/chargers/freshness").json() == {
        "latest_synced_at": None,
        "oldest_synced_at": None,
        "station_count": 0,
        "stale_count": 0,
    }


def test_freshness_is_one_query(client, db_session, monkeypatch):
    from sqlalchemy import event

    station(db_session, "A", 3)
    statements: list[str] = []
    engine = db_session.get_bind()

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        client.get("/api/chargers/freshness")
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert len([s for s in statements if "charger_cache" in s]) == 1
