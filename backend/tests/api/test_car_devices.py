"""와트잇 BE-5 기기 토큰 발급과 IP별 발급 한도."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select
from starlette.requests import Request

from evcharge.api import car_devices
from evcharge.api.car_devices import bearer_token, ip_key
from evcharge.api.routes import car
from evcharge.domain.pricing import KST
from evcharge.infra.models import CarDevice, CarDeviceRateLimit
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


def test_ip_key_is_hmac_with_the_server_secret(client, db_session, monkeypatch):
    monkeypatch.setenv("CAR_IP_HASH_SECRET", "test-secret")
    # TestClient는 uvicorn의 프록시 헤더 처리를 거치지 않아 접속 주소가 "testclient"다.
    ip = "testclient"
    expected = hmac.new(b"test-secret", ip.encode(), hashlib.sha256).hexdigest()

    assert ip_key(ip) == expected
    assert ip_key(ip) != hashlib.sha256(ip.encode()).hexdigest()

    client.post("/api/car/devices")
    keys = db_session.scalars(select(CarDeviceRateLimit.ip_hash)).all()
    assert expected in keys
    assert hashlib.sha256(ip.encode()).hexdigest() not in keys


def test_ip_key_without_secret_is_sha256_and_warns_once(monkeypatch, caplog):
    monkeypatch.setenv("CAR_IP_HASH_SECRET", "")
    monkeypatch.setattr(car_devices, "_warned_without_secret", False)

    with caplog.at_level(logging.WARNING, logger="evcharge.api.car_devices"):
        first = ip_key("198.51.100.7")
        ip_key("198.51.100.8")

    assert first == hashlib.sha256(b"198.51.100.7").hexdigest()
    warnings = [r for r in caplog.records if "CAR_IP_HASH_SECRET" in r.getMessage()]
    assert len(warnings) == 1
    assert "198.51.100" not in caplog.text
