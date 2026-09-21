"""``uv run python -m evcharge.sync`` — 캐시 수집 실행 진입점 (F-07).

DB도 공공 API도 건드리지 않는다. 진입점이 **무엇을 어떤 인자로 부르는지**만
본다. 실제 수집 로직은 tests/infra/test_charger_sync.py가 검증한다.
"""

from __future__ import annotations

import logging

import pytest

from evcharge import sync
from evcharge.settings import Settings


class _Recorder:
    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return sync.StationSyncResult(api_rows=1, stations=1, chargers=1, dropped_rows=0)


@pytest.fixture
def _no_db(monkeypatch):
    """세션을 여는 자리를 가짜로 바꾼다 — 진입점 테스트는 DB가 필요 없다."""
    import contextlib

    @contextlib.contextmanager
    def fake_scope():
        yield object()

    monkeypatch.setattr(sync, "session_scope", fake_scope)


def _settings(**overrides) -> Settings:
    values = {"charger_api_key": "key", "charger_zcodes": "12"}
    values.update(overrides)
    return Settings(**values)


def test_parse_zcodes_splits_and_trims():
    assert sync.parse_zcodes(" 12, 51 ,52 ") == ["12", "51", "52"]


def test_parse_zcodes_drops_empties():
    assert sync.parse_zcodes("12,,") == ["12"]


def test_missing_api_key_does_nothing_and_says_why(monkeypatch, caplog):
    monkeypatch.setattr(sync, "get_settings", lambda: _settings(charger_api_key=""))
    called = _Recorder()
    monkeypatch.setattr(sync, "sync_stations", called)

    with caplog.at_level(logging.ERROR):
        exit_code = sync.main([])

    # 조용히 0으로 끝나면 cron이 "수집되고 있다"고 착각한다.
    assert exit_code == 1
    assert called.calls == []
    assert "CHARGER_API_KEY" in caplog.text


def test_default_run_collects_full_station_details(monkeypatch, _no_db):
    monkeypatch.setattr(sync, "get_settings", lambda: _settings())
    stations = _Recorder()
    monkeypatch.setattr(sync, "sync_stations", stations)

    assert sync.main([]) == 0

    (_session, api, zcodes), _kwargs = stations.calls[0]
    assert zcodes == ["12"]
    assert api.service_key == "key"


def test_states_flag_takes_the_cheap_path(monkeypatch, _no_db):
    monkeypatch.setattr(sync, "get_settings", lambda: _settings(charger_zcodes="12,51"))
    states = _Recorder()
    states.result = sync.StatusSyncResult(
        api_rows=1, stations_updated=1, chargers_updated=1, unknown_rows=0
    )
    monkeypatch.setattr(
        sync,
        "sync_states",
        lambda *a, **kw: (states.calls.append((a, kw)), states.result)[1],
    )
    never = _Recorder()
    monkeypatch.setattr(sync, "sync_stations", never)

    assert sync.main(["--states", "--period", "5"]) == 0

    (_session, _api, zcodes), kwargs = states.calls[0]
    assert zcodes == ["12", "51"]
    assert kwargs["period"] == 5
    assert never.calls == []


def test_zcodes_can_be_overridden_on_the_command_line(monkeypatch, _no_db):
    monkeypatch.setattr(sync, "get_settings", lambda: _settings())
    stations = _Recorder()
    monkeypatch.setattr(sync, "sync_stations", stations)

    assert sync.main(["--zcodes", "51,52"]) == 0

    (_session, _api, zcodes), _kwargs = stations.calls[0]
    assert zcodes == ["51", "52"]


def test_api_failure_is_reported_as_a_failed_exit_code(monkeypatch, _no_db, caplog):
    monkeypatch.setattr(sync, "get_settings", lambda: _settings())

    def boom(*args, **kwargs):
        raise sync.ChargerApiError("getChargerInfo resultCode=30: <SERVICE_KEY>")

    monkeypatch.setattr(sync, "sync_stations", boom)

    with caplog.at_level(logging.ERROR):
        exit_code = sync.main([])

    assert exit_code == 1
    assert "resultCode=30" in caplog.text


def test_httpx_request_logging_is_silenced(monkeypatch, _no_db):
    """httpx는 INFO 레벨로 "HTTP Request: GET <전체 URL>"을 찍고, 그 URL 쿼리에
    serviceKey가 들어 있다. 실제로 터미널에 인증키가 그대로 찍히는 것을 보고
    막았다 — 진입점이 로깅을 켜는 자리에서 함께 잠가야 한다."""
    monkeypatch.setattr(sync, "get_settings", lambda: _settings())
    monkeypatch.setattr(sync, "sync_stations", _Recorder())
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.INFO)

    try:
        assert sync.main([]) == 0
        assert httpx_logger.level >= logging.WARNING
    finally:
        httpx_logger.setLevel(logging.NOTSET)
