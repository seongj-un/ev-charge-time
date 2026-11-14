"""설정 파일(요금, 공휴일, 공공 충전 단가)이 없거나 깨졌을 때의 응답.

응답에는 일반 문구만 나가고 서버 경로는 로그에만 남는다.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from evcharge.api.deps import get_holidays, get_public_prices, get_tariff
from evcharge.api.routes import car
from evcharge.domain.calendar import YamlHolidayProvider
from evcharge.domain.errors import TariffConfigError
from evcharge.domain.pricing import KST
from evcharge.domain.public_prices import PublicPrices
from evcharge.domain.tariff import Tariff

PLAN = {"soc_now": 32, "battery_capacity_wh": 77400, "depart_at": "2026-11-17T08:00:00+09:00"}
PUBLIC = {
    "place": "public",
    "soc_now": 30,
    "battery_capacity_wh": 77400,
    "payment": "nonmember",
    "charger_speed": "slow",
}
BROKEN_YAML = "version: [unclosed\n  - : :\n"


@pytest.fixture(autouse=True)
def _fixed_now_and_fresh_caches(monkeypatch):
    monkeypatch.setattr(car, "now_kst", lambda: datetime(2026, 11, 16, 18, tzinfo=KST))
    for cached in (get_tariff, get_holidays, get_public_prices):
        cached.cache_clear()
    yield
    for cached in (get_tariff, get_holidays, get_public_prices):
        cached.cache_clear()


def _point(monkeypatch, tmp_path, env: str, content: str | None):
    path = tmp_path / "secret-dir" / "config.yaml"
    path.parent.mkdir()
    if content is not None:
        path.write_text(content, encoding="utf-8")
    monkeypatch.setenv(env, str(path))
    return path


@pytest.mark.parametrize("content", [None, BROKEN_YAML, "- just\n- a list\n"])
@pytest.mark.parametrize(
    ("env", "url", "body", "detail"),
    [
        ("TARIFF_PATH", "/api/car/plan", PLAN, "요금 설정을 읽지 못했습니다."),
        ("HOLIDAYS_PATH", "/api/car/plan", PLAN, "공휴일 설정을 읽지 못했습니다."),
        (
            "PUBLIC_PRICES_PATH",
            "/api/car/leak-check",
            PUBLIC,
            "공공 충전 단가 설정을 읽지 못했습니다.",
        ),
    ],
)
def test_config_errors_answer_a_generic_500_and_log_the_path(
    client, monkeypatch, tmp_path, caplog, env, url, body, detail, content
):
    path = _point(monkeypatch, tmp_path, env, content)

    with caplog.at_level(logging.ERROR, logger="evcharge.api.errors"):
        response = client.post(url, json=body)

    assert response.status_code == 500
    assert response.json() == {"detail": detail}
    assert str(tmp_path) not in response.text
    assert "secret-dir" not in response.text
    assert str(path) in caplog.text


@pytest.mark.parametrize(
    ("loader", "source"),
    [
        (Tariff.load, "tariff"),
        (YamlHolidayProvider.load, "holidays"),
        (PublicPrices.load, "public_prices"),
    ],
)
def test_broken_yaml_is_a_config_error_with_its_source(tmp_path, loader, source):
    path = tmp_path / "broken.yaml"
    path.write_text(BROKEN_YAML, encoding="utf-8")

    with pytest.raises(TariffConfigError) as caught:
        loader(path)

    assert caught.value.source == source
    # 경로는 로그용 문구에만 있다 (응답에는 api/errors.py가 일반 문구를 쓴다).
    assert str(path) in str(caught.value)


def test_normal_requests_are_unchanged(client):
    assert client.post("/api/car/plan", json=PLAN).status_code == 200
    assert client.post("/api/car/leak-check", json=PUBLIC).status_code == 200
