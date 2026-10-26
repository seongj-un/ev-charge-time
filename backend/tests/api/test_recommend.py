import pytest
from fastapi.testclient import TestClient

from evcharge.main import create_app

SPEC_EXAMPLE = {
    "battery_kwh": 70,
    "soc_now": 30,
    "soc_target": 60,
    "charger_kw": 7,
    "earliest_start": "2026-10-07T18:00",
    "deadline": "2026-10-08T08:00",
}


def post(client, **overrides):
    return client.post("/api/recommend", json={**SPEC_EXAMPLE, **overrides})


def test_spec_example_reproduces(client):
    """API 명세서 2-2의 예시 요청을 그대로 보낸다."""
    response = post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["best"]["energy_kwh"] == pytest.approx(21.0)
    assert body["candidates_checked"] == 45
    assert body["best"]["start"] == "2026-10-07T22:00:00+09:00"
    assert body["best"]["end"] == "2026-10-08T01:00:00+09:00"
    assert body["baseline_now"]["start"] == "2026-10-07T18:00:00+09:00"
    assert body["savings_won"] > 0
    assert (
        body["savings_won"]
        == body["baseline_now"]["cost_won"] - body["best"]["cost_won"]
    )
    assert len(body["assumptions"]) >= 3
    assert "public_fast.base_price_per_kwh" in body["unverified_tariff_items"]


def test_naive_input_is_read_as_kst(client):
    body = post(client).json()
    assert body["baseline_now"]["start"].endswith("+09:00")


def test_explicit_timezone_is_respected(client):
    body = post(
        client,
        earliest_start="2026-10-07T09:00:00+00:00",  # = KST 18:00
        deadline="2026-10-07T23:00:00+00:00",
    ).json()

    assert body["baseline_now"]["start"] == "2026-10-07T18:00:00+09:00"


def test_business_error_returns_a_detail_string(client):
    response = post(client, deadline="2026-10-07T20:00")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert "시간이 부족합니다" in response.json()["detail"]


def test_validation_error_returns_a_detail_array(client):
    response = post(client, soc_target=20)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_target_must_exceed_current_soc(client):
    response = post(client, soc_now=60, soc_target=60)
    assert response.status_code == 422


def test_deadline_must_follow_earliest_start(client):
    response = post(client, deadline="2026-10-07T17:00")
    assert response.status_code == 422


def test_mode_defaults_to_self_low(client):
    assert post(client).status_code == 200
    assert post(client, mode="self_low").json() == post(client).json()


def test_battery_and_charger_are_required_without_a_vehicle(client):
    payload = dict(SPEC_EXAMPLE)
    del payload["battery_kwh"]
    response = client.post("/api/recommend", json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_vehicle_id_requires_login(client):
    response = post(client, vehicle_id="v_01")
    assert response.status_code == 401


# ── I-4: 요청 기간 상한 ──────────────────────────────────────────────────
#
# 리뷰어 실측: 9년 구간 = 12.6초/265MB/후보 315,533개, 인증이 필요 없는
# POST /api/recommend에서. 상한값(14일) 근거는 fix-batch-5-report.md 참고 —
# 이 서비스의 실제 용례(퇴근 후 귀가 → 다음날 출근, 주말 낮 구간)는 며칠을
# 넘지 않지만, 정당한 사용(예: 여행 중 숙소에 며칠 머물며 미리 계획)을 막지
# 않도록 여유를 뒀다.


def test_span_at_the_cap_boundary_is_200(client):
    response = post(
        client,
        earliest_start="2026-10-01T00:00",
        deadline="2026-10-15T00:00",  # earliest_start로부터 정확히 14일
    )
    assert response.status_code == 200


def test_span_one_minute_over_the_cap_is_422(client):
    response = post(
        client,
        earliest_start="2026-10-01T00:00",
        deadline="2026-10-15T00:01",  # 14일 + 1분
    )
    assert response.status_code == 422


def test_extreme_span_is_rejected_immediately_not_computed(client):
    """9999년 deadline(스키마가 그대로 받던 값)도 계산 없이 즉시 422여야
    한다 — 계산이 시작되면 그 자체로 리소스 소모(DoS)가 이미 일어난 것."""
    response = post(client, earliest_start="2026-01-01T00:00", deadline="9999-12-31T00:00")
    assert response.status_code == 422


def test_guest_recommend_never_opens_a_db_session(monkeypatch):
    """vehicle_id가 없는 게스트 요청은 DB 세션을 아예 열지 않아야 한다.

    ``conftest.client``는 ``get_session``을 테스트용으로 오버라이드해 버려서
    (``app.dependency_overrides``) 실제 ``get_sessionmaker`` 호출 여부를 가리므로
    여기서는 오버라이드가 없는 순수 ``create_app()``을 직접 써서 프로덕션과
    같은 의존성 해석 경로를 그대로 탄다. ``get_sessionmaker``가 호출되면 즉시
    실패시켜서, guest 경로가 DB 커넥션 풀에 손도 대지 않는다는 것을 Postgres
    유무와 무관하게 증명한다(1번 수정). 수정 전에는 ``Depends(get_session)``이
    매 요청마다 무조건 해석돼 이 테스트가 (AssertionError로) 실패했다.
    """

    def _fail(*args, **kwargs):
        raise AssertionError("guest 요청인데 DB 세션을 열려고 했다")

    monkeypatch.setattr("evcharge.infra.db.get_sessionmaker", _fail)

    raw_client = TestClient(create_app())
    response = post(raw_client)

    assert response.status_code == 200


# ── 무한대·극단값은 계산으로 넘기지 않는다 ──────────────────────────────────
#
# gt=0만 있으면 "Infinity"가 통과한다. charger_kw=Infinity면 충전 시간 0초·비용
# 0원이 200으로 나갔고, battery_kwh=1e300이면 timedelta가 넘쳐 500이 났다.


@pytest.mark.parametrize("field", ["battery_kwh", "charger_kw", "public_base_price"])
@pytest.mark.parametrize("value", ["Infinity", "-Infinity", "NaN"])
def test_non_finite_numbers_are_422(client, field, value):
    overrides = {field: value}
    if field == "public_base_price":
        overrides["mode"] = "public_fast"

    response = post(client, **overrides)

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["soc_now", "soc_target", "efficiency"])
def test_non_finite_soc_and_efficiency_are_422(client, field):
    assert post(client, **{field: "NaN"}).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"battery_kwh": 1e300},  # 필요한 충전 시간이 timedelta 범위를 넘는다
        {"charger_kw": 1e-300},  # 같은 결과를 반대쪽에서
        {"charger_kw": 1e300},
        {"public_base_price": 1e300, "mode": "public_fast"},
    ],
)
def test_absurd_magnitudes_are_422_not_500(client, overrides):
    response = post(client, **overrides)

    assert response.status_code == 422
    assert response.status_code != 500
