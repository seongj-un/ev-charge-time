"""F-07 캐시 수집기.

공공 API는 **충전기 1대당 1행**을 준다. 한 충전소(statId)에 여러 충전기가
달리므로 충전소 단위로 묶어 캐시 1행으로 저장하는 것이 이 모듈의 일이다.

여기서도 실제 API는 부르지 않는다 — 고정 행을 돌려주는 가짜 클라이언트를 쓴다.
"""

from __future__ import annotations

from evcharge.infra.charger_sync import build_station_records, sync_states, sync_stations
from evcharge.infra.models import ChargerCache


def info_row(**overrides) -> dict:
    """getChargerInfo 한 행. 실제 응답에서 옮긴 필드 구성이다."""
    row = {
        "statNm": "압해읍사무소",
        "statId": "ME174085",
        "chgerId": "01",
        "chgerType": "06",
        "addr": "전남광주통합특별시 신안군 압해읍 학교리 585",
        "addrDetail": "",
        "lat": "34.8654674",
        "lng": "126.3127835",
        "useTime": "24시간 이용가능",
        "busiId": "ME",
        "bnm": "기후에너지환경부",
        "busiNm": "기후에너지환경부",
        "stat": "2",
        "statUpdDt": "20260921212933",
        "output": "50",
        "zcode": "12",
    }
    row.update(overrides)
    return row


def status_row(**overrides) -> dict:
    """getChargerStatus 한 행. 상태만 온다."""
    row = {
        "busiId": "ME",
        "statId": "ME174085",
        "chgerId": "01",
        "stat": "3",
        "statUpdDt": "20260921221500",
    }
    row.update(overrides)
    return row


class FakeChargerApi:
    """호출 인자를 기록하는 가짜 클라이언트."""

    def __init__(self, info_rows=None, status_rows=None):
        self._info_rows = info_rows or []
        self._status_rows = status_rows or []
        self.info_calls: list[str] = []
        self.status_calls: list[tuple[str, int]] = []

    def fetch_station_rows(self, zcode: str) -> list[dict]:
        self.info_calls.append(zcode)
        return list(self._info_rows)

    def fetch_status_rows(self, zcode: str, period: int) -> list[dict]:
        self.status_calls.append((zcode, period))
        return list(self._status_rows)


# ---------------------------------------------------------------------------
# 행 → 충전소 문서 (순수 변환)
# ---------------------------------------------------------------------------


def test_multiple_chargers_collapse_into_one_station():
    records = build_station_records(
        [
            info_row(chgerId="01"),
            info_row(chgerId="02", stat="3"),
            info_row(statId="ME178024", statNm="함평천지 휴게소", chgerId="01"),
        ]
    )

    by_id = {record.station_id: record for record in records}
    assert len(by_id) == 2
    assert [charger["charger_id"] for charger in by_id["ME174085"].data["chargers"]] == ["01", "02"]
    assert len(by_id["ME178024"].data["chargers"]) == 1


def test_document_has_exactly_the_shape_stationout_reads():
    (record,) = build_station_records([info_row()])

    assert record.station_id == "ME174085"
    assert record.lat == 34.8654674
    assert record.lng == 126.3127835
    assert record.data == {
        "name": "압해읍사무소",
        "address": "전남광주통합특별시 신안군 압해읍 학교리 585",
        "lat": 34.8654674,
        "lng": 126.3127835,
        "operator": "기후에너지환경부",
        "available_hours": "24시간 이용가능",
        "chargers": [
            {
                "charger_id": "01",
                "type": "06",
                "capacity_kw": 50.0,
                "status": "2",
                "status_updated_at": "2026-09-21T21:29:33+09:00",
            }
        ],
    }


def test_unknown_status_code_is_passed_through_verbatim():
    """실제 데이터의 11.9%가 `9`다. 공식 활용가이드가 없는 상태에서 추정 매핑을
    넣으면 '사용 가능'이라 적힌 자리에 사용자가 헛걸음한다."""
    (record,) = build_station_records([info_row(stat="9")])

    assert record.data["chargers"][0]["status"] == "9"


def test_address_detail_is_appended_when_present():
    (record,) = build_station_records([info_row(addrDetail="지하 1층 주차장")])

    assert record.data["address"].endswith("585 지하 1층 주차장")


def test_rows_without_usable_coordinates_are_dropped():
    # 좌표가 없으면 반경 조회에 쓸 수 없고 StationOut의 lat/lng도 못 채운다.
    records = build_station_records(
        [info_row(statId="NO-LAT", lat=""), info_row(statId="BAD-LNG", lng="없음"), info_row()]
    )

    assert [record.station_id for record in records] == ["ME174085"]


def test_unparseable_status_time_becomes_null_not_now():
    (record,) = build_station_records([info_row(statUpdDt="")])

    assert record.data["chargers"][0]["status_updated_at"] is None


def test_missing_output_does_not_drop_the_charger():
    (record,) = build_station_records([info_row(output="")])

    assert record.data["chargers"][0]["capacity_kw"] == 0.0


# ---------------------------------------------------------------------------
# 캐시 쓰기
# ---------------------------------------------------------------------------


def test_sync_stations_fills_the_cache_and_the_coordinate_columns(db_session):
    api = FakeChargerApi(info_rows=[info_row(chgerId="01"), info_row(chgerId="02")])

    result = sync_stations(db_session, api, ["12"])

    assert api.info_calls == ["12"]
    assert result.stations == 1
    assert result.chargers == 2
    cached = db_session.get(ChargerCache, "ME174085")
    assert cached is not None
    # 컬럼으로도 꺼내 둔다 — 반경 조회의 1차 필터가 인덱스를 타야 한다.
    assert cached.lat == 34.8654674
    assert cached.lng == 126.3127835
    assert cached.data["name"] == "압해읍사무소"


def test_sync_stations_is_idempotent(db_session):
    api = FakeChargerApi(info_rows=[info_row()])
    sync_stations(db_session, api, ["12"])

    renamed = FakeChargerApi(info_rows=[info_row(statNm="압해읍사무소(이전)")])
    sync_stations(db_session, renamed, ["12"])

    rows = db_session.query(ChargerCache).all()
    assert len(rows) == 1
    assert rows[0].data["name"] == "압해읍사무소(이전)"


def test_sync_stations_visits_every_zcode(db_session):
    api = FakeChargerApi(info_rows=[info_row()])

    sync_stations(db_session, api, ["12", "51"])

    assert api.info_calls == ["12", "51"]


def test_sync_states_updates_only_the_status_fields(db_session):
    sync_stations(db_session, FakeChargerApi(info_rows=[info_row(chgerId="01")]), ["12"])

    api = FakeChargerApi(status_rows=[status_row(chgerId="01", stat="3")])
    result = sync_states(db_session, api, ["12"], period=10)

    assert api.status_calls == [("12", 10)]
    assert result.chargers_updated == 1
    charger = db_session.get(ChargerCache, "ME174085").data["chargers"][0]
    assert charger["status"] == "3"
    assert charger["status_updated_at"] == "2026-09-21T22:15:00+09:00"
    # 상태만 갱신한다 — 이름·용량은 전체 수집이 채운 값 그대로여야 한다.
    assert charger["capacity_kw"] == 50.0
    assert db_session.get(ChargerCache, "ME174085").data["name"] == "압해읍사무소"


def test_sync_states_ignores_stations_that_are_not_cached_yet(db_session):
    api = FakeChargerApi(status_rows=[status_row(statId="NOT-CACHED")])

    result = sync_states(db_session, api, ["12"], period=10)

    assert result.chargers_updated == 0
    assert result.unknown_rows == 1
    assert db_session.get(ChargerCache, "NOT-CACHED") is None


def test_sync_states_ignores_a_charger_id_the_cache_has_never_seen(db_session):
    sync_stations(db_session, FakeChargerApi(info_rows=[info_row(chgerId="01")]), ["12"])

    api = FakeChargerApi(status_rows=[status_row(chgerId="99")])
    result = sync_states(db_session, api, ["12"], period=10)

    # 상태 응답에는 종류·용량이 없어서 새 충전기를 만들 수 없다. 전체 수집이 채운다.
    assert result.unknown_rows == 1
    assert [c["charger_id"] for c in db_session.get(ChargerCache, "ME174085").data["chargers"]] == [
        "01"
    ]
