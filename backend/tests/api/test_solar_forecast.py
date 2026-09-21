"""F-09 태양광 발전 예측 (``GET /api/solar-forecast``).

**실제 기상청 API를 부르지 않는다.** ``KmaApi`` 프로토콜을 만족하는 가짜
클라이언트를 끼운다 — 수집기(``charger_sync``)가 쓰는 것과 같은 방식이다.

절대값이 아니라 성질을 본다: 밤은 0, 흐린 날 < 맑은 날, 정오가 최대.
물리 모델 자체의 불변식은 ``tests/domain/test_solar.py``에 있고, 여기서는
그 성질이 **HTTP 응답까지 살아서 나오는지**를 확인한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from evcharge.api.routes.extensions import get_solar_service, kma_api_key
from evcharge.api.solar_service import SolarForecastService
from evcharge.domain.pricing import KST
from evcharge.infra.kma_api import KmaNoDataError
from evcharge.main import create_app

# 실측에서 22:18에 고른 발표와 같은 상황(2300은 아직 안정되지 않음).
NOW = datetime(2026, 9, 21, 22, 30, tzinfo=KST)

CATEGORIES = ("TMP", "REH", "WSD", "POP")


class FakeKmaClient:
    """고정 응답을 돌려주는 가짜. 호출 인자를 기록해 캐시 동작까지 본다."""

    def __init__(self, sky: str = "1", pty: str = "0", *, available: set | None = None,
                 overrides: dict | None = None, days: int = 3,
                 truncated: dict | None = None):
        self.sky = sky
        self.pty = pty
        # None이면 어떤 발표든 응답한다. 집합이면 그 (base_date, base_time)만.
        self.available = available
        # {(fcstDate, fcstTime): (sky, pty)} — 특정 시간대만 다르게.
        self.overrides = overrides or {}
        self.days = days
        # {(base_date, base_time): 시간대 수} — 실측에서 본 '반쯤 쓰인' 응답을
        # 재현한다(resultCode는 00인데 행이 모자란다).
        self.truncated = truncated or {}
        self.calls: list[tuple] = []

    def fetch_village_forecast(
        self, nx: int, ny: int, base_date: str, base_time: str
    ) -> list[dict]:
        self.calls.append((nx, ny, base_date, base_time))
        if self.available is not None and (base_date, base_time) not in self.available:
            raise KmaNoDataError("자료 없음")

        start = datetime.strptime(base_date + base_time, "%Y%m%d%H%M") + timedelta(hours=1)
        slots = self.truncated.get((base_date, base_time), self.days * 24)
        rows: list[dict] = []
        for step in range(slots):
            slot = start + timedelta(hours=step)
            key = (slot.strftime("%Y%m%d"), slot.strftime("%H%M"))
            sky, pty = self.overrides.get(key, (self.sky, self.pty))
            for category, value in (("SKY", sky), ("PTY", pty)):
                rows.append(
                    {
                        "baseDate": base_date, "baseTime": base_time,
                        "category": category, "fcstDate": key[0], "fcstTime": key[1],
                        "fcstValue": value, "nx": nx, "ny": ny,
                    }
                )
            # 쓰지 않는 항목도 실려 오는 것이 실제 응답이다.
            for category in CATEGORIES:
                rows.append(
                    {
                        "baseDate": base_date, "baseTime": base_time,
                        "category": category, "fcstDate": key[0], "fcstTime": key[1],
                        "fcstValue": "0", "nx": nx, "ny": ny,
                    }
                )
        return rows


def make_client(
    service: SolarForecastService | None = None, *, key: str = "test-key"
) -> TestClient:
    app = create_app()
    app.dependency_overrides[kma_api_key] = lambda: key
    if service is not None:
        app.dependency_overrides[get_solar_service] = lambda: service
    return TestClient(app)


def service_with(fake: FakeKmaClient, **kwargs) -> SolarForecastService:
    return SolarForecastService(client=fake, clock=lambda: NOW, **kwargs)


def get(client: TestClient, region: str = "전남", day: str = "2026-09-22"):
    return client.get("/api/solar-forecast", params={"region": region, "day": day})


# ── 키가 없으면 501 ──────────────────────────────────────────────────────


def test_returns_501_without_an_api_key():
    """``charger_api_key``와 같은 규칙: 키가 없으면 기능 자체가 성립하지 않는다."""
    response = get(make_client(key=""))

    assert response.status_code == 501
    assert isinstance(response.json()["detail"], str)


def test_invalid_day_format_is_422():
    response = get(make_client(service_with(FakeKmaClient())), day="2026-13-99")

    assert response.status_code == 422


# ── 응답 모양 ────────────────────────────────────────────────────────────


def test_returns_an_hourly_forecast_for_the_day():
    response = get(make_client(service_with(FakeKmaClient())))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["region"] == "전남"
    assert body["day"] == "2026-09-22"
    assert body["model_version"]
    assert [h["hour"] for h in body["hours"]] == list(range(24))


def test_reports_which_grid_cell_and_issuance_it_used():
    """한 격자가 시도 전체를 대신한다는 사실을 응답이 숨기지 않는다."""
    body = get(make_client(service_with(FakeKmaClient()))).json()

    assert body["grid_nx"] > 0
    assert body["grid_ny"] > 0
    assert body["base_date"] == "20260921"
    assert body["base_time"] == "2000"
    assert any("격자" in note for note in body["assumptions"])


def test_naju_and_bitgaram_resolve_to_the_same_grid():
    """대회 지역(빛가람/나주)이 반드시 동작해야 한다."""
    client = make_client(service_with(FakeKmaClient()))

    naju = get(client, region="나주").json()
    bitgaram = get(client, region="빛가람").json()

    assert (naju["grid_nx"], naju["grid_ny"]) == (bitgaram["grid_nx"], bitgaram["grid_ny"])
    assert naju["hours"]


def test_unknown_region_is_rejected_with_the_known_list():
    response = get(make_client(service_with(FakeKmaClient())), region="아무데나")

    assert response.status_code == 422
    assert "전남" in response.json()["detail"]


# ── 물리 불변식이 HTTP까지 살아 나오는지 ────────────────────────────────


def test_night_hours_are_zero_and_noon_is_the_peak():
    hours = get(make_client(service_with(FakeKmaClient()))).json()["hours"]
    by_hour = {h["hour"]: h["ghi_wm2"] for h in hours}

    for hour in (0, 1, 2, 3, 22, 23):
        assert by_hour[hour] == 0.0
    assert max(by_hour, key=lambda h: by_hour[h]) in (12, 13)


def test_an_overcast_day_stays_below_a_clear_day():
    clear = get(make_client(service_with(FakeKmaClient(sky="1")))).json()["hours"]
    cloudy = get(make_client(service_with(FakeKmaClient(sky="4")))).json()["hours"]

    noon_clear = next(h for h in clear if h["hour"] == 12)
    noon_cloudy = next(h for h in cloudy if h["hour"] == 12)

    assert 0 < noon_cloudy["ghi_wm2"] < noon_clear["ghi_wm2"]
    # 맑은날 일사량은 하늘 상태와 무관하게 같다 — 감쇠만 달라진다.
    assert noon_cloudy["clear_sky_ghi_wm2"] == pytest.approx(noon_clear["clear_sky_ghi_wm2"])


def test_rain_attenuates_more_than_a_merely_overcast_sky():
    overcast = get(make_client(service_with(FakeKmaClient(sky="4", pty="0")))).json()["hours"]
    rain = get(make_client(service_with(FakeKmaClient(sky="4", pty="1")))).json()["hours"]

    assert next(h for h in rain if h["hour"] == 12)["ghi_wm2"] < next(
        h for h in overcast if h["hour"] == 12
    )["ghi_wm2"]


def test_output_index_is_the_irradiance_against_stc():
    hours = get(make_client(service_with(FakeKmaClient()))).json()["hours"]
    noon = next(h for h in hours if h["hour"] == 12)

    assert noon["output_index"] == pytest.approx(noon["ghi_wm2"] / 1000.0)
    assert 0.0 < noon["output_index"] <= 1.0


def test_raw_sky_and_pty_codes_are_passed_through():
    """감쇠가 맞는지 사람이 되짚을 수 있게 원본 코드를 그대로 싣는다."""
    noon = next(
        h
        for h in get(make_client(service_with(FakeKmaClient(sky="3", pty="0")))).json()["hours"]
        if h["hour"] == 12
    )

    assert noon["sky"] == "3"
    assert noon["pty"] == "0"


# ── predicted_mwh: 설비용량이 없으면 null ────────────────────────────────


def test_predicted_mwh_is_null_without_installed_capacity():
    """설비용량 자료가 없으면 MWh를 지어내지 않는다 — null로 비운다."""
    body = get(make_client(service_with(FakeKmaClient()))).json()

    assert body["installed_capacity_mw"] is None
    assert all(h["predicted_mwh"] is None for h in body["hours"])
    assert any("설비용량" in note for note in body["assumptions"])


def test_predicted_mwh_is_filled_when_capacity_and_source_are_configured():
    service = service_with(
        FakeKmaClient(), capacities={"전남": 1000.0}, capacity_source="테스트 출처 2026-09"
    )
    body = get(make_client(service)).json()

    assert body["installed_capacity_mw"] == 1000.0
    assert body["capacity_source"] == "테스트 출처 2026-09"

    noon = next(h for h in body["hours"] if h["hour"] == 12)
    assert noon["predicted_mwh"] is not None
    assert noon["predicted_mwh"] > 0
    # 밤은 발전량도 0이다.
    assert next(h for h in body["hours"] if h["hour"] == 0)["predicted_mwh"] == 0.0


def test_predicted_mwh_scales_linearly_with_capacity():
    small = get(
        make_client(service_with(FakeKmaClient(), capacities={"전남": 100.0}, capacity_source="s"))
    ).json()
    big = get(
        make_client(service_with(FakeKmaClient(), capacities={"전남": 200.0}, capacity_source="s"))
    ).json()

    noon_small = next(h for h in small["hours"] if h["hour"] == 12)["predicted_mwh"]
    noon_big = next(h for h in big["hours"] if h["hour"] == 12)["predicted_mwh"]

    # 응답 값은 소수 3자리로 반올림해서 나가므로, 두 배가 정확히 맞아떨어지지
    # 않을 수 있다(각자 따로 반올림된다). 선형성만 보면 되므로 그만큼 허용한다.
    assert noon_big == pytest.approx(noon_small * 2, abs=0.002)


def test_capacity_without_a_source_is_ignored():
    """출처를 적을 수 없는 값은 쓰지 않는다.

    이 저장소는 요금 잠정치에도 ``source``와 ``status``를 달아 왔다. 근거 없는
    설비용량으로 MWh를 내보내면 '지어낸 숫자'와 구별되지 않는다.
    """
    service = service_with(FakeKmaClient(), capacities={"전남": 1000.0}, capacity_source="")
    body = get(make_client(service)).json()

    assert body["installed_capacity_mw"] is None
    assert all(h["predicted_mwh"] is None for h in body["hours"])


def test_capacity_configured_for_another_region_does_not_leak():
    service = service_with(FakeKmaClient(), capacities={"제주": 500.0}, capacity_source="s")
    body = get(make_client(service), region="전남").json()

    assert body["installed_capacity_mw"] is None


# ── 발표 선택·되돌아가기·캐시 ────────────────────────────────────────────


def test_falls_back_to_an_older_issuance_when_the_latest_has_no_data():
    """가장 최근 발표가 NO_DATA면 이전 발표로 물러선다."""
    fake = FakeKmaClient(available={("20260921", "1700")})
    body = get(make_client(service_with(fake))).json()

    assert body["base_time"] == "1700"
    assert [call[3] for call in fake.calls] == ["2000", "1700"]


def test_gives_up_with_503_when_no_issuance_has_data():
    fake = FakeKmaClient(available=set())
    response = get(make_client(service_with(fake)))

    assert response.status_code == 503
    assert isinstance(response.json()["detail"], str)


def test_the_issuance_is_fetched_once_and_then_cached():
    """예보는 하루 여덟 번만 갱신된다. 요청마다 부르면 할당량 낭비다."""
    fake = FakeKmaClient()
    client = make_client(service_with(fake))

    get(client)
    get(client)
    get(client, day="2026-09-23")

    assert len(fake.calls) == 1


def test_a_different_region_is_fetched_separately():
    fake = FakeKmaClient()
    client = make_client(service_with(fake))

    get(client, region="전남")
    get(client, region="제주")

    assert len(fake.calls) == 2


# ── 자료가 없는 날짜·시간대 ─────────────────────────────────────────────


def test_a_day_beyond_the_forecast_horizon_is_422():
    """시간별 자료는 발표일+2일까지다. 그 너머는 '없다'고 분명히 말한다."""
    response = get(make_client(service_with(FakeKmaClient())), day="2026-10-30")

    assert response.status_code == 422
    assert "예보" in response.json()["detail"]


def test_a_partial_day_returns_only_the_hours_that_exist():
    """'오늘'은 발표 시각 이후 시간대만 있다. 없는 시간대를 지어내지 않는다."""
    body = get(make_client(service_with(FakeKmaClient())), day="2026-09-21").json()

    # 2000 발표는 오늘 21·22·23시만 싣는다.
    assert [h["hour"] for h in body["hours"]] == [21, 22, 23]
    assert any("일부" in note for note in body["assumptions"])


def test_an_unknown_sky_code_drops_that_hour_instead_of_guessing():
    """모르는 코드에 그럴듯한 감쇠를 매기지 않는다 — 그 시간대만 뺀다.

    충전소 ``stat`` 코드에서 문서에 없는 값이 11.9%였던 전례가 있다.
    """
    fake = FakeKmaClient(overrides={("20260922", "1200"): ("2", "0")})
    body = get(make_client(service_with(fake))).json()

    hours = [h["hour"] for h in body["hours"]]
    assert 12 not in hours
    assert 11 in hours and 13 in hours
    assert any("하늘상태" in note for note in body["assumptions"])


# ── 실측에서 본 '오류 없이 일부만 오는' 응답 ────────────────────────────


def test_an_incomplete_issuance_is_rejected_and_the_previous_one_is_used():
    """가장 최근 발표가 ``resultCode=00``이면서도 잘려 올 수 있다.

    실측(2026-09-21 22:10): 같은 요청에 ``base_time=2300``이 408행과 980행을
    번갈아 돌려줬고 **둘 다 00**이었다. "오류 없이 일부만 온다"가 가장 위험한
    실패 모양이라 — 조용히 구멍 난 예보를 내보내게 된다 — 하루를 못 채운
    응답은 쓰지 않고 이전 발표로 물러선다.
    """
    fake = FakeKmaClient(truncated={("20260921", "2000"): 10})
    body = get(make_client(service_with(fake))).json()

    assert body["base_time"] == "1700"
    assert [h["hour"] for h in body["hours"]] == list(range(24))


def test_an_incomplete_issuance_is_not_cached():
    """잘린 응답을 캐시에 넣으면 그 발표가 끝날 때까지 계속 틀린 답을 준다."""
    fake = FakeKmaClient(truncated={("20260921", "2000"): 10})
    service = service_with(fake)
    client = make_client(service)

    get(client)
    first_round = [call[3] for call in fake.calls]
    fake.calls.clear()
    get(client)
    second_round = [call[3] for call in fake.calls]

    assert first_round == ["2000", "1700"]
    # 잘린 2000은 캐시에 없으므로 다시 시도하고, 온전한 1700은 캐시에서 나온다.
    assert second_round == ["2000"]


# ── 설정 ────────────────────────────────────────────────────────────────


def test_kma_key_is_normalized_like_the_charger_key():
    """포털은 계정당 키가 하나라 두 설정에 같은 문자열이 들어간다.

    Encoding/Decoding 두 형태를 똑같이 받아줘야 "충전소는 되는데 예보는
    인증 실패"라는 상황이 생기지 않는다.
    """
    from evcharge.settings import Settings

    assert Settings(kma_api_key="abc%2Bdef%3D").kma_api_key == "abc+def="
    assert Settings(kma_api_key='  "abc+def="  ').kma_api_key == "abc+def="
    assert Settings(kma_api_key="").kma_api_key == ""


def test_capacity_setting_is_parsed_as_region_to_megawatts():
    from evcharge.api.solar_service import parse_capacities

    assert parse_capacities("전남:1234.5,광주:210") == {"전남": 1234.5, "광주": 210.0}
    assert parse_capacities("") == {}


def test_malformed_capacity_entries_are_skipped_not_fatal():
    """설정 오타 하나로 서버가 안 뜨는 것보다, 그 지역만 null이 낫다."""
    from evcharge.api.solar_service import parse_capacities

    assert parse_capacities("전남:1000,쓰레기,광주:abc,제주:500") == {
        "전남": 1000.0,
        "제주": 500.0,
    }
