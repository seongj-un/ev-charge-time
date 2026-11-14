"""와트잇 BE-5 기기 토큰 발급과 IP별 발급 한도."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select
from starlette.requests import Request

from evcharge.api.car_devices import bearer_token
from evcharge.api.routes import car
from evcharge.domain.pricing import KST
from evcharge.infra.models import CarDevice
from evcharge.infra.security import hash_token

NOW = datetime(2026, 11, 17, 18, 0, tzinfo=KST)


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(car, "now_kst", lambda: NOW)
    monkeypatch.delenv("CAR_DEVICE_RATE_LIMIT_COUNT", raising=False)
    monkeypatch.delenv("CAR_DEVICE_RATE_LIMIT_WINDOW_MINUTES", raising=False)


def test_register_device_returns_a_token_once_and_stores_only_its_hash(client, db_session):
    response = client.post("/api/car/devices")

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"device_id", "device_token"}
    uuid.UUID(body["device_id"])
    assert len(body["device_token"]) >= 40

    device = db_session.scalar(select(CarDevice).where(CarDevice.id == body["device_id"]))
    assert device is not None
    assert device.token_hash == hash_token(body["device_token"])
    assert body["device_token"] not in device.token_hash


def test_each_registration_gets_a_new_device(client):
    first = client.post("/api/car/devices").json()
    second = client.post("/api/car/devices").json()

    assert first["device_id"] != second["device_id"]
    assert first["device_token"] != second["device_token"]


def test_registration_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setenv("CAR_DEVICE_RATE_LIMIT_COUNT", "2")
    monkeypatch.setenv("CAR_DEVICE_RATE_LIMIT_WINDOW_MINUTES", "60")

    assert client.post("/api/car/devices").status_code == 201
    assert client.post("/api/car/devices").status_code == 201
    refused = client.post("/api/car/devices")

    assert refused.status_code == 429
    assert isinstance(refused.json()["detail"], str)
    # 18:00은 60분 창의 시작이라 다음 창까지 1시간이다.
    assert refused.headers["retry-after"] == "3600"

    # 창이 넘어가면 다시 1부터 센다.
    monkeypatch.setattr(car, "now_kst", lambda: datetime(2026, 11, 17, 19, 0, tzinfo=KST))
    assert client.post("/api/car/devices").status_code == 201


def _request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw})


@pytest.mark.parametrize(
    ("headers", "token"),
    [
        ({}, None),
        ({"Authorization": "Bearer abc"}, "abc"),
        ({"Authorization": "bearer  abc "}, "abc"),
        ({"Authorization": "Basic abc"}, None),
        ({"Authorization": "Bearer"}, None),
        ({"Authorization": "Bearer "}, None),
        ({"Authorization": "Bearer " + "x" * 257}, None),
    ],
)
def test_bearer_token_parsing(headers, token):
    assert bearer_token(_request(headers)) == token
