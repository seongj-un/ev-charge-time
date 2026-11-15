"""F-07 캐시 수집기.

공공 API는 **충전기 1대당 1행**을 준다. 한 충전소(statId)에 여러 충전기가
달리므로 충전소 단위로 묶어 캐시 1행으로 저장하는 것이 이 모듈의 일이다.

여기서도 실제 API는 부르지 않는다 — 고정 행을 돌려주는 가짜 클라이언트를 쓴다.
"""

from __future__ import annotations

import pytest

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


# ---------------------------------------------------------------------------
# 상태 확인 시각 (BE-10)
# ---------------------------------------------------------------------------


def _confirmed(db_session):
    from evcharge.infra.models import ChargerSyncState

    db_session.expire_all()
    state = db_session.get(ChargerSyncState, "status")
    return None if state is None else state.confirmed_at


def _set_confirmed(db_session, minutes_ago: int) -> None:
    from sqlalchemy import text

    db_session.execute(
        text(
            "INSERT INTO charger_sync_state (kind, confirmed_at) VALUES ('status', "
            "clock_timestamp() - make_interval(mins => :m)) ON CONFLICT (kind) DO UPDATE "
            "SET confirmed_at = excluded.confirmed_at"
        ),
        {"m": minutes_ago},
    )


def test_full_sync_sets_the_confirmed_time(db_session):
    from datetime import datetime, timedelta

    sync_stations(db_session, FakeChargerApi(info_rows=[info_row()]), ["12"])

    confirmed = _confirmed(db_session)
    assert confirmed is not None
    assert abs(datetime.now(confirmed.tzinfo) - confirmed) < timedelta(minutes=1)


def test_status_sync_without_a_starting_point_confirms_nothing(db_session):
    sync_states(db_session, FakeChargerApi(), ["12"], period=10)

    assert _confirmed(db_session) is None


@pytest.mark.parametrize(("last_minutes_ago", "advances"), [(5, True), (9, True), (11, False)])
def test_status_sync_advances_only_over_a_continuous_window(db_session, last_minutes_ago, advances):
    _set_confirmed(db_session, last_minutes_ago)
    before = _confirmed(db_session)

    sync_states(db_session, FakeChargerApi(), ["12"], period=10)

    assert (_confirmed(db_session) > before) is advances


def test_a_failed_status_sync_confirms_nothing(db_session):
    _set_confirmed(db_session, 5)
    before = _confirmed(db_session)

    class Broken(FakeChargerApi):
        def fetch_status_rows(self, zcode, period):
            raise RuntimeError("api down")

    with pytest.raises(RuntimeError):
        sync_states(db_session, Broken(), ["12"], period=10)

    assert _confirmed(db_session) == before


def test_full_sync_marks_its_start_equal_to_the_rows_it_wrote(db_session):
    from datetime import datetime, timedelta

    from evcharge.domain.pricing import KST
    from evcharge.infra.models import ChargerSyncState

    gone_at = datetime.now(KST) - timedelta(days=3)
    db_session.add(
        ChargerCache(
            station_id="GONE", data={"chargers": []}, lat=35.0, lng=126.8, updated_at=gone_at
        )
    )
    db_session.commit()

    sync_stations(db_session, FakeChargerApi(info_rows=[info_row()]), ["12"])

    db_session.expire_all()
    mark = db_session.get(ChargerSyncState, "stations").confirmed_at
    assert db_session.get(ChargerCache, "ME174085").updated_at == mark
    assert db_session.get(ChargerCache, "GONE").updated_at < mark


# ---------------------------------------------------------------------------
# 끊김 뒤 전체 수집으로 되살리기 (BE-10 리뷰)
# ---------------------------------------------------------------------------


def _runs(db_session):
    from evcharge.infra.models import ChargerFullSyncRun

    db_session.expire_all()
    return [run.recovery for run in db_session.query(ChargerFullSyncRun).order_by("id")]


def test_a_gap_is_recovered_by_a_full_sync(db_session):
    from datetime import datetime, timedelta

    _set_confirmed(db_session, 16)  # 5분 주기 상태 수집이 두 번 빠졌다
    api = FakeChargerApi(info_rows=[info_row()])

    result = sync_states(db_session, api, ["12"], period=10, recover_daily_max=4)

    assert result.confirmed is False
    assert result.recovered is not None and result.recovered.stations == 1
    assert api.info_calls == ["12"]
    confirmed = _confirmed(db_session)
    assert abs(datetime.now(confirmed.tzinfo) - confirmed) < timedelta(minutes=1)
    assert _runs(db_session) == [True]


def test_status_sync_before_any_full_sync_recovers_too(db_session):
    api = FakeChargerApi(info_rows=[info_row()])

    result = sync_states(db_session, api, ["12"], period=10, recover_daily_max=4)

    assert result.recovered is not None
    assert _confirmed(db_session) is not None


def test_no_recovery_over_a_continuous_window(db_session):
    _set_confirmed(db_session, 5)
    api = FakeChargerApi(info_rows=[info_row()])

    result = sync_states(db_session, api, ["12"], period=10, recover_daily_max=4)

    assert (result.confirmed, result.recovered, api.info_calls) == (True, None, [])


def test_recovery_stops_at_the_daily_full_sync_limit(db_session, caplog):
    from evcharge.infra.charger_sync import record_full_sync_run

    for _ in range(4):
        record_full_sync_run(db_session, recovery=False)
    _set_confirmed(db_session, 16)
    before = _confirmed(db_session)
    api = FakeChargerApi(info_rows=[info_row()])

    with caplog.at_level("WARNING"):
        result = sync_states(db_session, api, ["12"], period=10, recover_daily_max=4)

    assert (result.confirmed, result.recovered, api.info_calls) == (False, None, [])
    assert _confirmed(db_session) == before
    assert "한도 4" in caplog.text
    assert len(_runs(db_session)) == 4


def test_below_the_limit_recovers(db_session):
    from evcharge.infra.charger_sync import record_full_sync_run

    for _ in range(3):
        record_full_sync_run(db_session, recovery=False)
    _set_confirmed(db_session, 16)
    api = FakeChargerApi(info_rows=[info_row()])

    sync_states(db_session, api, ["12"], period=10, recover_daily_max=4)

    assert api.info_calls == ["12"]
    assert _runs(db_session) == [False, False, False, True]


def test_a_failed_recovery_still_counts_against_the_limit(db_session):
    _set_confirmed(db_session, 16)

    class Broken(FakeChargerApi):
        def fetch_station_rows(self, zcode):
            raise RuntimeError("api down")

    with pytest.raises(RuntimeError):
        sync_states(db_session, Broken(), ["12"], period=10, recover_daily_max=4)

    assert _runs(db_session) == [True]


def test_without_a_limit_a_gap_is_left_alone(db_session):
    _set_confirmed(db_session, 16)
    api = FakeChargerApi(info_rows=[info_row()])

    result = sync_states(db_session, api, ["12"], period=10)

    assert (result.recovered, api.info_calls) == (None, [])


# ---------------------------------------------------------------------------
# 상태 반영 지연 로그 (BE-10 리뷰)
# ---------------------------------------------------------------------------


def test_status_lag_is_received_minus_the_operator_time():
    from datetime import datetime

    from evcharge.domain.pricing import KST
    from evcharge.infra.charger_sync import status_lag_minutes

    received = datetime(2026, 9, 21, 22, 20, 0, tzinfo=KST)
    rows = [
        status_row(statUpdDt="20260921221500"),
        status_row(statUpdDt="20260921220530"),
        status_row(statUpdDt="20260921222100"),  # 운영기관 시계가 1분 빠름
        status_row(statUpdDt="garbage"),
    ]

    assert status_lag_minutes(rows, received_at=received) == [5.0, 14.5, -1.0]


def test_status_sync_logs_one_lag_line_without_station_ids(db_session, caplog, monkeypatch):
    from datetime import datetime

    from evcharge.domain.pricing import KST
    from evcharge.infra import charger_sync

    monkeypatch.setattr(charger_sync, "_now", lambda: datetime(2026, 9, 21, 22, 20, 0, tzinfo=KST))
    rows = [
        status_row(chgerId="01", statUpdDt="20260921221500"),
        status_row(chgerId="02", statUpdDt="20260921221000"),
        status_row(chgerId="03", statUpdDt="20260921215000"),
    ]

    with caplog.at_level("INFO", logger="evcharge.infra.charger_sync"):
        sync_states(db_session, FakeChargerApi(status_rows=rows), ["12"], period=10)

    lines = [r.getMessage() for r in caplog.records if "반영 지연" in r.getMessage()]
    assert lines == ["상태 반영 지연: 3행, 중앙값 10.0분, 최대 30.0분"]
    assert "ME174085" not in caplog.text
