from datetime import datetime

import pytest

from evcharge.api.car_leak_service import compute_leak_check, default_depart_at, is_leaking
from evcharge.api.deps import get_public_prices
from evcharge.api.routes import car
from evcharge.api.schemas import CarLeakCheckRequest
from evcharge.domain.pricing import KST

# 2026-11-16(월) 18:00, 겨울 평일 최대부하. 밤 10시 경부하까지 기다리면 아낀다.
MONDAY_EVENING = datetime(2026, 11, 16, 18, 0, tzinfo=KST)

HOME = {"soc_now": 20, "battery_capacity_wh": 77400}
PUBLIC = {"place": "public", "soc_now": 30, "battery_capacity_wh": 70000}

# config/public_charging_prices.yaml (한국소비자원 2025-12-17, 원/kWh)
SLOW = {"member": 293.3, "roaming": 397.9, "nonmember": 446.0}
FAST = {"member": 358.1, "roaming": 418.5, "nonmember": 466.5}


def kst(*args: int) -> datetime:
    return datetime(*args, tzinfo=KST)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(car, "now_kst", lambda: MONDAY_EVENING)
    monkeypatch.delenv("CAR_LEAK_MIN_WON", raising=False)


def post(client, body):
    return client.post("/api/car/leak-check", json={k: v for k, v in body.items() if v is not None})


# ── home: 시간대 ───────────────────────────────────────────────────────


def test_home_leaking_matches_car_plan(client):
    body = post(client, {**HOME, "depart_at": "2026-11-17T08:00"}).json()
    plan = client.post(
        "/api/car/plan", json={**HOME, "depart_at": "2026-11-17T08:00"}
    ).json()

    assert body["leaking"] is True
    assert body["cause"] == "time"
    assert body["leak_won"] == plan["savings_won"] >= 500
    assert body["plan"] == plan["plan"]
    assert body["reservation"] == plan["reservation"]
    assert body["energy_kwh"] == plan["plan"]["energy_kwh"]
    assert body["unit_price_now"] is None and body["unit_price_member"] is None
    assert body["speech"] == (
        "지금은 요금이 비싼 시간이라 돈이 새고 있어요. "
        f"오늘 밤 10시부터 충전하면 약 {body['leak_won']:,}원 아낄 수 있어요. "
        "차량 예약 충전을 밤 10시 시작, 새벽 4시 39분 종료로 설정해 주세요."
    )


def test_home_small_saving_is_not_leaking(client, monkeypatch):
    # 2026-10-07(수) 18:00 봄·가을. 같은 조건에서 아끼는 돈이 500원이 안 된다.
    monkeypatch.setattr(car, "now_kst", lambda: kst(2026, 10, 7, 18))
    body = post(client, {"soc_now": 30, "battery_capacity_wh": 70000}).json()

    assert 0 < body["leak_won"] < 500
    assert body["leaking"] is False
    assert body["cause"] is None
    assert body["plan"] is None and body["reservation"] is None
    assert body["speech"] == "지금 충전해도 괜찮아요."


def test_home_without_depart_assumes_the_next_8am(client):
    assumed = post(client, HOME).json()
    explicit = post(client, {**HOME, "depart_at": "2026-11-17T08:00"}).json()

    assert assumed["leak_won"] == explicit["leak_won"]
    assert assumed["reservation"] == explicit["reservation"]
    assert "출발 시각 미입력: 11월 17일 오전 8시(KST) 출발로 가정" in assumed["assumptions"]
    assert not any("미입력" in item for item in explicit["assumptions"])


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (kst(2026, 11, 16, 18), kst(2026, 11, 17, 8)),
        (kst(2026, 11, 16, 1, 30), kst(2026, 11, 16, 8)),
        (kst(2026, 11, 16, 8), kst(2026, 11, 17, 8)),
        (kst(2026, 11, 16, 7, 59), kst(2026, 11, 16, 8)),
        (kst(2026, 12, 31, 23), kst(2027, 1, 1, 8)),
    ],
)
def test_default_depart_is_the_first_8am_after_now(now, expected):
    assert default_depart_at(now) == expected


def test_home_insufficient_time_says_keep_charging(client):
    body = post(client, {**HOME, "depart_at": "2026-11-16T20:00"})

    assert body.status_code == 200
    assert body.json()["leaking"] is False
    assert body.json()["leak_won"] == 0
    assert body.json()["speech"] == "출발 전까지 목표만큼 채우려면 지금 바로 충전해야 해요."


def test_home_target_reached_needs_no_charging(client):
    body = post(client, {**HOME, "soc_now": 85}).json()

    assert body["leaking"] is False
    assert body["energy_kwh"] == 0
    assert body["speech"] == "이미 목표 잔량 80%에 닿아서 더 충전하지 않아도 돼요."


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"depart_at": "2026-11-16T17:00"}, "depart_at은 현재 시각보다 뒤여야 합니다."),
        ({"depart_at": "2026-11-19T18:01"}, "72시간을 넘을 수 없습니다."),
    ],
)
def test_home_reuses_car_plan_time_checks(client, overrides, message):
    response = post(client, {**HOME, **overrides})

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["body", "depart_at"]
    assert message in error["msg"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"battery_capacity_wh": 999},
        {"soc_now": 100},
        {"soc_target": 0},
        {"charger_kw": 0},
        {"place": "garage"},
        {"payment": "card"},
        {"charger_speed": "ultra"},
        {"mode": "fast"},
    ],
)
def test_out_of_range_input_is_422(client, overrides):
    assert post(client, {**HOME, **overrides}).status_code == 422


# ── public: 결제 방식 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("speed", "table"), [("slow", SLOW), ("fast", FAST)]
)
@pytest.mark.parametrize("payment", ["roaming", "nonmember"])
def test_public_pricier_payment_is_leaking(client, speed, table, payment):
    body = post(client, {**PUBLIC, "payment": payment, "charger_speed": speed}).json()

    # 70kWh × (80 - 30)% = 35kWh
    expected = round(35.0 * (table[payment] - table["member"]))
    assert body["energy_kwh"] == pytest.approx(35.0)
    assert body["leak_won"] == expected
    assert body["leaking"] is True
    assert body["cause"] == "payment"
    assert body["unit_price_now"] == table[payment]
    assert body["unit_price_member"] == table["member"]
    assert body["plan"] is None and body["reservation"] is None
    label = {"roaming": "로밍가", "nonmember": "비회원가"}[payment]
    assert body["speech"] == (
        f"{label}로 충전하고 있어서 돈이 새고 있어요. "
        f"이번 충전(약 35kWh)은 회원가보다 약 {expected:,}원 더 나와요. "
        "이 충전소 사업자 회원으로 결제하면 아낄 수 있어요. 사업자 평균 기준 추정이에요."
    )
    assert "한국소비자원 2025-12-17 발표 20개 사업자 평균 단가 기준 추정" in body["assumptions"]


@pytest.mark.parametrize("speed", ["slow", "fast"])
def test_public_member_is_not_leaking(client, speed):
    body = post(client, {**PUBLIC, "payment": "member", "charger_speed": speed}).json()

    assert body["leaking"] is False
    assert body["leak_won"] == 0
    assert body["cause"] is None
    assert body["unit_price_now"] == body["unit_price_member"]
    assert body["speech"] == "지금 충전해도 괜찮아요."


def test_public_unverified_fast_price_is_named_in_assumptions(client):
    fast = post(client, {**PUBLIC, "payment": "roaming", "charger_speed": "fast"}).json()
    slow = post(client, {**PUBLIC, "payment": "roaming", "charger_speed": "slow"}).json()

    assert "급속 평균 단가는 소비자원 원문과 아직 대조하지 못한 값" in fast["assumptions"]
    assert not any("대조하지 못한" in item for item in slow["assumptions"])


@pytest.mark.parametrize(
    ("battery_wh", "leak_won", "leaking"),
    [
        # 비회원 완속 차이 152.7원/kWh. 3.274kWh × 152.7 = 499.94 → 500원
        (3274, 500, True),
        # 3.27kWh × 152.7 = 499.33 → 499원
        (3270, 499, False),
    ],
)
def test_public_threshold_is_inclusive_at_exactly_500(client, battery_wh, leak_won, leaking):
    body = post(
        client,
        {
            "place": "public",
            "soc_now": 0,
            "soc_target": 100,
            "battery_capacity_wh": battery_wh,
            "payment": "nonmember",
            "charger_speed": "slow",
        },
    ).json()

    assert body["leak_won"] == leak_won
    assert body["leaking"] is leaking


def test_public_small_charge_speaks_one_decimal_kwh(client):
    body = post(
        client,
        {**PUBLIC, "battery_capacity_wh": 10000, "soc_target": 72.5, "payment": "nonmember",
         "charger_speed": "fast"},
    ).json()

    # 10kWh × 42.5% = 4.25kWh, 4.25 × 108.4 = 460.7 → 461원 (기준 500원 미만)
    assert body["energy_kwh"] == pytest.approx(4.25)
    assert body["leak_won"] == 461
    assert body["leaking"] is False


@pytest.mark.parametrize(
    ("missing", "field"),
    [
        ({"payment": None, "charger_speed": "slow"}, "payment"),
        ({"payment": "member", "charger_speed": None}, "charger_speed"),
        ({"payment": None, "charger_speed": None}, "payment"),
    ],
)
def test_public_requires_payment_and_charger_speed(client, missing, field):
    response = post(client, {**PUBLIC, **missing})

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["loc"] == ["body", field]
    assert error["msg"] == f"place가 public이면 {field}가 필요합니다."


def test_public_ignores_home_only_fields(client):
    # 공공 충전기는 시간대 계산을 하지 않으므로 depart_at을 보지 않는다.
    body = post(
        client,
        {**PUBLIC, "payment": "roaming", "charger_speed": "slow",
         "depart_at": "2020-01-01T08:00", "mode": "self_high"},
    )

    assert body.status_code == 200
    assert body.json()["cause"] == "payment"


def test_public_target_reached_needs_no_charging(client):
    body = post(
        client, {**PUBLIC, "soc_now": 90, "payment": "nonmember", "charger_speed": "slow"}
    ).json()

    assert body["leaking"] is False
    assert body["leak_won"] == 0
    assert body["unit_price_now"] == SLOW["nonmember"]
    assert body["speech"] == "이미 목표 잔량 80%에 닿아서 더 충전하지 않아도 돼요."


# ── 기준 금액 설정 ─────────────────────────────────────────────────────


def test_min_won_comes_from_settings(client, monkeypatch):
    monkeypatch.setenv("CAR_LEAK_MIN_WON", "6000")
    body = post(client, {**PUBLIC, "payment": "nonmember", "charger_speed": "slow"}).json()

    assert body["leak_won"] == 5344
    assert body["leaking"] is False


def test_zero_leak_never_counts_even_with_a_zero_threshold():
    assert is_leaking(0, 0) is False
    assert is_leaking(1, 0) is True
    assert is_leaking(500, 500) is True
    assert is_leaking(499, 500) is False


def test_compute_leak_check_takes_injected_threshold():
    payload = CarLeakCheckRequest(**PUBLIC, payment="roaming", charger_speed="slow")
    leaky = compute_leak_check(
        payload, MONDAY_EVENING, min_won=3661, load_prices=get_public_prices
    )
    quiet = compute_leak_check(
        payload, MONDAY_EVENING, min_won=3662, load_prices=get_public_prices
    )

    # 35kWh × (397.9 - 293.3) = 3,661원
    assert leaky.leak_won == quiet.leak_won == 3661
    assert leaky.leaking is True and quiet.leaking is False


def test_speeches_have_no_markdown_or_symbols(client):
    speeches = [
        post(client, HOME).json()["speech"],
        post(client, {**PUBLIC, "payment": "nonmember", "charger_speed": "fast"}).json()["speech"],
    ]
    for speech in speeches:
        assert not set(speech) & set("*#`_[]<>|~")


@pytest.fixture
def broken_price_file(monkeypatch, tmp_path):
    get_public_prices.cache_clear()
    monkeypatch.setenv("PUBLIC_PRICES_PATH", str(tmp_path / "missing.yaml"))
    yield
    get_public_prices.cache_clear()


def test_home_does_not_read_the_public_price_file(client, broken_price_file):
    response = post(client, {**HOME, "depart_at": "2026-11-17T08:00"})

    assert response.status_code == 200
    assert response.json()["leaking"] is True


def test_public_fails_on_a_broken_price_file(client, broken_price_file):
    response = post(client, {**PUBLIC, "payment": "roaming", "charger_speed": "slow"})

    assert response.status_code == 500
