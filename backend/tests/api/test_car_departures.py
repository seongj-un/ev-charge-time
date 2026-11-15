"""와트잇 BE-8 출발 기록·삭제·제안 API (``/api/car/departures``)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from evcharge.api.car_departures import record_stated
from evcharge.api.routes import car
from evcharge.domain.pricing import KST
from evcharge.infra.models import CarDeparture, CarDevice
from evcharge.infra.security import hash_token

OBSERVED_MAX, STATED_MAX = 10, 5  # 설정 기본값

# 2026-11-19(목) 21:00. 제안 기본 날짜는 내일 11-20(금).
NOW = datetime(2026, 11, 19, 21, 0, tzinfo=KST)
URL = "/api/car/departures"


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(car, "now_kst", lambda: NOW)


def register(client) -> dict[str, str]:
    body = client.post("/api/car/devices").json()
    return {"Authorization": f"Bearer {body['device_token']}"}


def kst(*args) -> datetime:
    return datetime(*args, tzinfo=KST)


def depart(client, headers, moment: datetime):
    return client.post(URL, json={"departed_at": moment.isoformat()}, headers=headers)


def rows(db_session) -> list[CarDeparture]:
    return list(db_session.scalars(select(CarDeparture).order_by(CarDeparture.departed_at)))


def device_of(db_session, headers) -> CarDevice:
    token = headers["Authorization"].split()[1]
    return db_session.scalar(select(CarDevice).where(CarDevice.token_hash == hash_token(token)))


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", URL), ("delete", URL), ("get", f"{URL}/suggest")],
)
def test_token_is_required(client, method, path):
    kwargs = {"json": {"departed_at": "2026-11-19T07:30"}} if method == "post" else {}

    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_records_an_observed_departure(client, db_session):
    headers = register(client)

    response = depart(client, headers, kst(2026, 11, 19, 7, 31))

    assert response.status_code == 201
    body = response.json()
    assert body["departed_at"] == "2026-11-19T07:31:00+09:00"
    assert (body["source"], body["merged"]) == ("observed", False)
    assert [(r.departed_at, r.source, r.recorded_at) for r in rows(db_session)] == [
        (kst(2026, 11, 19, 7, 31), "observed", NOW)
    ]


def test_offsetless_time_is_read_as_kst(client, db_session):
    headers = register(client)

    depart_body = client.post(URL, json={"departed_at": "2026-11-19T07:31"}, headers=headers)

    assert depart_body.json()["departed_at"] == "2026-11-19T07:31:00+09:00"


def test_observed_within_30_minutes_merge_and_keep_the_earlier(client, db_session):
    headers = register(client)
    depart(client, headers, kst(2026, 11, 19, 7, 40))

    merged = depart(client, headers, kst(2026, 11, 19, 7, 15))
    later = depart(client, headers, kst(2026, 11, 19, 7, 45))
    separate = depart(client, headers, kst(2026, 11, 19, 8, 16))

    assert (merged.status_code, merged.json()["merged"]) == (200, True)
    assert merged.json()["departed_at"] == "2026-11-19T07:15:00+09:00"
    assert (later.status_code, later.json()["departed_at"]) == (
        200,
        "2026-11-19T07:15:00+09:00",
    )
    assert separate.status_code == 201
    assert [r.departed_at for r in rows(db_session)] == [
        kst(2026, 11, 19, 7, 15),
        kst(2026, 11, 19, 8, 16),
    ]


def test_observed_replaces_a_stated_time_nearby(client, db_session):
    headers = register(client)
    device = device_of(db_session, headers)
    record_stated(db_session, device, kst(2026, 11, 19, 7, 30), NOW)

    response = depart(client, headers, kst(2026, 11, 19, 7, 42))

    assert response.json()["merged"] is True
    assert [(r.departed_at, r.source) for r in rows(db_session)] == [
        (kst(2026, 11, 19, 7, 42), "observed")
    ]


def test_stated_does_not_replace_an_observed_time(client, db_session):
    headers = register(client)
    device = device_of(db_session, headers)
    depart(client, headers, kst(2026, 11, 19, 7, 42))

    record_stated(db_session, device, kst(2026, 11, 19, 7, 30), NOW)

    assert [(r.departed_at, r.source) for r in rows(db_session)] == [
        (kst(2026, 11, 19, 7, 42), "observed")
    ]


def test_a_later_statement_replaces_an_earlier_one(client, db_session):
    headers = register(client)
    device = device_of(db_session, headers)
    record_stated(db_session, device, kst(2026, 11, 20, 7, 30), NOW)

    record_stated(db_session, device, kst(2026, 11, 20, 7, 50), NOW)

    assert [(r.departed_at, r.source) for r in rows(db_session)] == [
        (kst(2026, 11, 20, 7, 50), "stated")
    ]


@pytest.mark.parametrize(
    ("moment", "message"),
    [
        (NOW + timedelta(minutes=6), "departed_at은 지금보다 늦을 수 없습니다."),
        (NOW - timedelta(days=91), "departed_at은 90일 안이어야 합니다."),
    ],
)
def test_future_and_too_old_times_are_422(client, db_session, moment, message):
    headers = register(client)

    response = depart(client, headers, moment)

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == message
    assert response.json()["detail"][0]["loc"] == ["body", "departed_at"]
    assert rows(db_session) == []


@pytest.mark.parametrize(
    "body",
    [
        {"departed_at": "9999-12-31T23:59:00+00:00"},
        {"departed_at": "2026-11-19T07:30", "source": "stated"},
        {},
    ],
)
def test_bad_bodies_are_422(client, body):
    response = client.post(URL, json=body, headers=register(client))

    assert response.status_code == 422


def test_observed_daily_limit_counts_new_records_only(client, db_session, monkeypatch):
    headers = register(client)
    for day in range(OBSERVED_MAX):
        assert depart(client, headers, kst(2026, 11, 9 + day, 7, 30)).status_code == 201
    merged = depart(client, headers, kst(2026, 11, 18, 7, 35))

    over = depart(client, headers, kst(2026, 11, 19, 7, 30))

    assert merged.status_code == 200
    assert over.status_code == 429
    assert over.json()["detail"] == (
        "오늘 남길 수 있는 출발 기록(10건)을 다 썼습니다. 내일 다시 보내 주세요."
    )
    assert over.headers["Retry-After"] == str(3 * 3600)  # 다음 날 0시까지
    assert len(rows(db_session)) == OBSERVED_MAX

    monkeypatch.setattr(car, "now_kst", lambda: NOW + timedelta(hours=3))
    assert depart(client, headers, kst(2026, 11, 19, 7, 30)).status_code == 201


def stated_times(count: int) -> list[datetime]:
    """30분 넘게 떨어진 서로 다른 말한 시각."""
    return [kst(2026, 11, 20, 6, 0) + timedelta(hours=hour) for hour in range(count)]


def test_stated_over_its_daily_limit_is_skipped_silently(client, db_session):
    device = device_of(db_session, register(client))

    saved = [record_stated(db_session, device, at, NOW) for at in stated_times(STATED_MAX + 1)]

    assert saved == [True] * STATED_MAX + [False]
    assert len(rows(db_session)) == STATED_MAX


def test_full_stated_quota_does_not_block_observed(client, db_session):
    headers = register(client)
    device = device_of(db_session, headers)
    for at in stated_times(STATED_MAX):
        record_stated(db_session, device, at, NOW)

    response = depart(client, headers, kst(2026, 11, 19, 7, 30))

    assert response.status_code == 201
    assert len(rows(db_session)) == STATED_MAX + 1


def test_full_observed_quota_does_not_block_stated(client, db_session):
    headers = register(client)
    device = device_of(db_session, headers)
    for day in range(OBSERVED_MAX):
        depart(client, headers, kst(2026, 11, 9 + day, 7, 30))

    assert record_stated(db_session, device, kst(2026, 11, 20, 7, 30), NOW) is True


def test_stated_limit_is_a_setting(client, db_session, monkeypatch):
    monkeypatch.setenv("CAR_DEPARTURE_DAILY_STATED_MAX", "2")
    device = device_of(db_session, register(client))

    saved = [record_stated(db_session, device, at, NOW) for at in stated_times(3)]

    assert saved == [True, True, False]


def test_records_older_than_90_days_are_removed_on_write(client, db_session):
    other = register(client)
    depart(client, other, kst(2026, 11, 19, 7, 0))
    db_session.execute(
        text(
            "INSERT INTO car_departures (id, device_id, departed_at, source, recorded_at) "
            "VALUES (:id, :device, :at, 'observed', :at)"
        ),
        {
            "id": str(uuid.uuid4()),
            "device": device_of(db_session, other).id,
            "at": NOW - timedelta(days=90, minutes=1),
        },
    )

    depart(client, register(client), kst(2026, 11, 19, 8, 0))

    assert len(rows(db_session)) == 2
    assert min(r.departed_at for r in rows(db_session)) == kst(2026, 11, 19, 7, 0)


def test_delete_removes_only_this_devices_records(client, db_session):
    mine, other = register(client), register(client)
    depart(client, mine, kst(2026, 11, 18, 7, 30))
    depart(client, mine, kst(2026, 11, 19, 7, 30))
    depart(client, other, kst(2026, 11, 19, 7, 30))

    response = client.delete(URL, headers=mine)
    again = client.delete(URL, headers=mine)

    assert response.json() == {"deleted": 2}
    assert again.json() == {"deleted": 0}
    assert [r.device_id for r in rows(db_session)] == [device_of(db_session, other).id]


# ── 제안 ─────────────────────────────────────────────────────────────────

WEEKDAYS = [kst(2026, 11, d, 7, 0) for d in (12, 13, 16, 17, 18)]  # 목금월화수


def seed(client, headers, minutes: list[int], days=WEEKDAYS):
    for day, minute in zip(days, minutes, strict=False):
        assert depart(client, headers, day + timedelta(minutes=minute)).status_code == 201


def suggest(client, headers, **params):
    return client.get(f"{URL}/suggest", params=params, headers=headers)


def test_high_confidence_suggestion_for_tomorrow(client):
    headers = register(client)
    seed(client, headers, [28, 31, 33, 40, 22])

    body = suggest(client, headers).json()

    assert body == {
        "date": "2026-11-20",
        "suggested_depart_at": "2026-11-20T07:30:00+09:00",
        "confidence": "high",
        "basis_count": 5,
        "day_type": "weekday",
        "speech": "내일도 오전 7시 30분에 출발하세요?",
    }


def test_low_confidence_suggestion(client):
    headers = register(client)
    seed(client, headers, [28, 31, 33])

    body = suggest(client, headers).json()

    assert (body["confidence"], body["basis_count"]) == ("low", 3)
    assert body["speech"] == "내일 오전 7시 30분쯤 출발하세요?"


def test_no_suggestion_and_other_devices_do_not_count(client):
    mine, other = register(client), register(client)
    seed(client, other, [28, 31, 33, 40, 22])
    seed(client, mine, [30, 30])

    body = suggest(client, mine).json()

    assert body["suggested_depart_at"] is None
    assert (body["confidence"], body["basis_count"]) == (None, 2)
    assert body["speech"] == "내일 몇 시에 출발하세요?"


def test_weekend_date_uses_weekend_records(client):
    headers = register(client)
    seed(client, headers, [28, 31, 33, 40, 22])
    weekend = [kst(2026, 11, d, 10, 0) for d in (7, 8, 14, 15)]
    seed(client, headers, [0, 5, 10, 0], days=weekend)

    body = suggest(client, headers, date="2026-11-21").json()

    assert body["day_type"] == "weekend_holiday"
    assert (body["suggested_depart_at"], body["basis_count"]) == (
        "2026-11-21T10:00:00+09:00",
        4,
    )
    assert body["speech"] == "11월 21일 오전 10시쯤 출발하세요?"


def test_christmas_counts_as_a_holiday(client):
    headers = register(client)

    body = suggest(client, headers, date="2026-12-25").json()  # 금요일 공휴일

    assert body["day_type"] == "weekend_holiday"


@pytest.mark.parametrize("value", ["2026-11-2", "2026-13-01", "tomorrow", "0001-01-01"])
def test_bad_dates_are_422(client, value):
    response = suggest(client, register(client), date=value)

    assert response.status_code == 422


def test_dates_without_holiday_data_are_422(client):
    response = suggest(client, register(client), date="2030-01-07")

    assert response.status_code == 422
    assert "2030년 공휴일 정보가 아직 없어서" in response.json()["detail"]


def test_parallel_records_of_one_departure_make_one_row(concurrent, monkeypatch):
    token = f"race-{uuid.uuid4()}"
    device_id = str(uuid.uuid4())
    setup = concurrent.session()
    try:
        setup.add(CarDevice(id=device_id, token_hash=hash_token(token)))
        setup.commit()
    finally:
        setup.close()

    def send(client) -> int:
        return client.post(
            URL,
            json={"departed_at": "2026-11-19T07:30:00+09:00"},
            headers={"Authorization": f"Bearer {token}"},
        ).status_code

    try:
        codes = concurrent.run(send, count=6)
        check = concurrent.session()
        try:
            count = check.scalar(
                select(func.count()).where(CarDeparture.device_id == device_id)
            )
        finally:
            check.close()
        assert sorted(codes) == [200, 200, 200, 200, 200, 201]
        assert count == 1
    finally:
        cleanup = concurrent.session()
        try:
            cleanup.execute(text("DELETE FROM car_devices WHERE id = :id"), {"id": device_id})
            cleanup.commit()
        finally:
            cleanup.close()


# ── stated: 계산 요청에 받은 출발 시각 ─────────────────────────────────────

PLAN = {"soc_now": 20, "battery_capacity_wh": 77400, "depart_at": "2026-11-20T07:30"}
HOME = {"place": "home", "soc_now": 20, "battery_capacity_wh": 77400}


def test_plan_with_a_token_records_the_stated_time_and_answers_the_same(client, db_session):
    plain = client.post("/api/car/plan", json=PLAN).json()
    assert rows(db_session) == []

    with_token = client.post("/api/car/plan", json=PLAN, headers=register(client)).json()

    assert {**with_token, "saving_id": None} == plain
    assert [(r.departed_at, r.source) for r in rows(db_session)] == [
        (kst(2026, 11, 20, 7, 30), "stated")
    ]


def test_plan_with_a_wrong_token_records_nothing(client, db_session):
    response = client.post(
        "/api/car/plan", json=PLAN, headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 200
    assert rows(db_session) == []


def test_repeated_plans_for_one_morning_make_one_record(client, db_session):
    headers = register(client)
    for depart_at in ("2026-11-20T07:30", "2026-11-20T07:40", "2026-11-20T07:40"):
        client.post("/api/car/plan", json={**PLAN, "depart_at": depart_at}, headers=headers)

    assert [(r.departed_at, r.source) for r in rows(db_session)] == [
        (kst(2026, 11, 20, 7, 40), "stated")
    ]


def test_leak_check_records_only_a_given_home_departure(client, db_session):
    headers = register(client)
    client.post("/api/car/leak-check", json=HOME, headers=headers)  # 가정한 08:00
    client.post(
        "/api/car/leak-check",
        json={"place": "public", "soc_now": 30, "battery_capacity_wh": 70000},
        headers=headers,
    )
    assert rows(db_session) == []

    client.post(
        "/api/car/leak-check", json={**HOME, "depart_at": "2026-11-20T06:50"}, headers=headers
    )

    assert [(r.departed_at, r.source) for r in rows(db_session)] == [
        (kst(2026, 11, 20, 6, 50), "stated")
    ]


def test_a_failed_stated_record_does_not_change_the_plan(client, db_session, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from evcharge.api import car_departures

    def broken(*args, **kwargs):
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(car_departures, "record_stated", broken)
    plain = client.post("/api/car/plan", json=PLAN).json()

    response = client.post("/api/car/plan", json=PLAN, headers=register(client))

    assert response.status_code == 200
    assert {**response.json(), "saving_id": None} == plain


# ── leak-check(home): depart_at이 없으면 평소 출발 시각(high)을 가정 ─────────

# 목요일 18:00(겨울 평일 최대부하). 지금 충전하면 돈이 샌다.
EVENING = kst(2026, 11, 19, 18, 0)
USUAL_ASSUMPTION = (
    "출발 시각 미입력: 평소 출발 시각(5건 기준)으로 11월 20일 오전 7시 30분(KST) 출발로 가정"
)


@pytest.fixture
def evening(monkeypatch):
    monkeypatch.setattr(car, "now_kst", lambda: EVENING)


def test_leak_check_assumes_the_usual_departure_when_confident(client, evening):
    headers = register(client)
    seed(client, headers, [28, 31, 33, 40, 22])

    body = client.post("/api/car/leak-check", json=HOME, headers=headers).json()

    assert body["leaking"] is True
    assert body["speech"].startswith("평소처럼 내일 오전 7시 30분 출발 기준으로, ")
    assert USUAL_ASSUMPTION in body["assumptions"]
    assert body["plan"]["end"] <= "2026-11-20T07:30:00+09:00"


def test_leak_check_keeps_8am_when_the_suggestion_is_low(client, evening):
    headers = register(client)
    seed(client, headers, [28, 31, 33])
    plain = client.post("/api/car/leak-check", json=HOME).json()

    body = client.post("/api/car/leak-check", json=HOME, headers=headers).json()

    assert body["speech"].startswith("내일 오전 8시 출발 기준으로, ")
    assert {**body, "saving_id": None} == plain


def test_leak_check_without_a_token_is_unchanged(client, evening):
    other = register(client)
    seed(client, other, [28, 31, 33, 40, 22])

    body = client.post("/api/car/leak-check", json=HOME).json()

    assert body["speech"].startswith("내일 오전 8시 출발 기준으로, ")
    assert body["saving_id"] is None


def test_given_depart_at_wins_over_the_usual_time(client, evening):
    headers = register(client)
    seed(client, headers, [28, 31, 33, 40, 22])

    body = client.post(
        "/api/car/leak-check", json={**HOME, "depart_at": "2026-11-20T09:00"}, headers=headers
    ).json()

    assert "평소" not in body["speech"]
    assert not any("미입력" in a for a in body["assumptions"])


def test_usual_departure_keeps_the_rule_of_never_stopping_a_short_charge(client, evening):
    """PR #15 규칙: 가정한 출발까지 못 채우면 멈추라 하지 않고 지금 충전을 계속하라고 한다."""
    headers = register(client)
    seed(client, headers, [28, 31, 33, 40, 22])

    body = client.post(
        "/api/car/leak-check", json={**HOME, "soc_now": 5, "charger_kw": 3}, headers=headers
    ).json()

    assert body["leaking"] is False
    assert body["speech"] == (
        "평소처럼 내일 오전 7시 30분에 출발하신다면 지금 바로 충전을 계속해야 해요. "
        "출발 시각을 알려 주시면 다시 계산해 드릴게요."
    )


def test_a_failing_suggestion_falls_back_to_8am(client, monkeypatch, evening):
    from sqlalchemy.exc import OperationalError

    from evcharge.api import car_departures

    headers = register(client)
    seed(client, headers, [28, 31, 33, 40, 22])

    def broken(*args, **kwargs):
        raise OperationalError("SELECT", {}, Exception("db down"))

    monkeypatch.setattr(car_departures, "suggestion_for", broken)

    response = client.post("/api/car/leak-check", json=HOME, headers=headers)

    assert response.status_code == 200
    assert response.json()["speech"].startswith("내일 오전 8시 출발 기준으로, ")


@pytest.mark.parametrize(
    ("now", "assumption"),
    [
        # 새벽: 오늘(20일 금) 아침
        (kst(2026, 11, 20, 1, 0), USUAL_ASSUMPTION),
        # 오늘(19일 목) 평소 출발은 지났고 오전 8시 기본 가정도 내일: 내일
        (kst(2026, 11, 19, 10, 0), USUAL_ASSUMPTION),
        (kst(2026, 11, 19, 13, 0), USUAL_ASSUMPTION),
        # 일요일 낮: 오늘(주말)은 제안이 없고 다음 날(월)의 평일 제안
        (
            kst(2026, 11, 22, 11, 0),
            "출발 시각 미입력: 평소 출발 시각(5건 기준)으로 11월 23일 오전 7시 30분(KST) "
            "출발로 가정",
        ),
        # 19일 07:40: 오늘 평소 출발(07:30)은 지났지만 기본 가정은 오늘 오전 8시다. 내일로
        # 늦추지 않는다.
        (kst(2026, 11, 19, 7, 40), "출발 시각 미입력: 11월 19일 오전 8시(KST) 출발로 가정"),
    ],
)
def test_next_usual_departure_never_skips_the_default_day(client, monkeypatch, now, assumption):
    headers = register(client)
    seed(client, headers, [28, 31, 33, 40, 22])
    monkeypatch.setattr(car, "now_kst", lambda: now)

    body = client.post("/api/car/leak-check", json=HOME, headers=headers).json()

    assert assumption in body["assumptions"]


def test_no_suggestion_on_the_default_day_keeps_8am(client, monkeypatch):
    """일요일 06:00, 주말 기록 없음: 월요일 평일 제안(high)이 있어도 하루 늦추지 않고 오늘 8시."""
    headers = register(client)
    seed(client, headers, [28, 31, 33, 40, 22])
    monkeypatch.setattr(car, "now_kst", lambda: kst(2026, 11, 22, 6, 0))

    body = client.post("/api/car/leak-check", json=HOME, headers=headers).json()

    assert body["assumptions"][-1] == "출발 시각 미입력: 11월 22일 오전 8시(KST) 출발로 가정"


def test_late_night_departures_give_no_suggestion_and_no_date_mismatch(client):
    headers = register(client)
    seed(client, headers, [16 * 60 + 56] * 5)  # 평일 23:56 출발 5건

    body = suggest(client, headers).json()

    assert body["date"] == "2026-11-20"
    assert (body["suggested_depart_at"], body["confidence"], body["basis_count"]) == (None, None, 5)
    assert body["speech"] == "내일 몇 시에 출발하세요?"


def test_failure_logs_carry_no_device_or_time(client, monkeypatch, caplog):
    """제약 위반 DETAIL에는 키 값이 있다. 로그에는 오류 종류만 남긴다."""
    from sqlalchemy.exc import IntegrityError

    from evcharge.api import car_departures

    detail = 'Key (device_id)=(dev-secret-123) at 2026-11-20 07:30 is not present in "car_devices".'

    def broken(*args, **kwargs):
        raise IntegrityError("INSERT INTO car_departures ...", {}, Exception(detail))

    monkeypatch.setattr(car_departures, "record_stated", broken)
    monkeypatch.setattr(car_departures, "suggestion_for", broken)
    headers = register(client)

    with caplog.at_level("WARNING", logger="evcharge.api.car_departures"):
        client.post("/api/car/plan", json=PLAN, headers=headers)
        client.post("/api/car/leak-check", json=HOME, headers=headers)

    messages = [r.getMessage() for r in caplog.records]
    assert any("IntegrityError" in m for m in messages)
    assert len(messages) >= 2
    joined = caplog.text
    assert "dev-secret-123" not in joined
    assert "07:30" not in joined
