import textwrap

import pytest

from evcharge.domain.errors import TariffConfigError
from evcharge.domain.tariff import Tariff


def write_yaml(tmp_path, body: str):
    path = tmp_path / "tariff.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_unverified_items_reports_dotted_paths(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: "test-1"
        vat_rate:
          value: 0.1
          source: "부가가치세법"
          status: verified
        adders:
          climate_env_per_kwh:
            value: 0.0
            source: "미확보"
            status: unverified
          fuel_adjustment_per_kwh:
            value: 0.0
            source: "미확보"
            status: derived
        """,
    )

    tariff = Tariff.load(path)

    assert tariff.unverified_items() == [
        "adders.climate_env_per_kwh",
        "adders.fuel_adjustment_per_kwh",
    ]


def test_verified_items_are_excluded(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: "test-1"
        vat_rate:
          value: 0.1
          source: "부가가치세법"
          status: verified
        """,
    )

    assert Tariff.load(path).unverified_items() == []


def test_unknown_status_is_rejected_at_load_time(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: "test-1"
        vat_rate:
          value: 0.1
          source: "부가가치세법"
          status: probably_fine
        """,
    )

    with pytest.raises(TariffConfigError) as excinfo:
        Tariff.load(path)

    assert "probably_fine" in str(excinfo.value)
    assert "vat_rate" in str(excinfo.value)


def test_version_is_exposed(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: "2026.1-draft"
        vat_rate:
          value: 0.1
          source: "부가가치세법"
          status: verified
        """,
    )

    assert Tariff.load(path).version == "2026.1-draft"


def test_real_config_flags_every_item_the_spec_lists_as_unverified():
    """API 명세서 2-1의 /health 예시에 적힌 5개 항목이 모두 잡혀야 한다."""
    from evcharge.settings import get_settings

    unverified = Tariff.load(get_settings().tariff_path).unverified_items()

    for expected in [
        "time_bands",
        "public_fast.base_price_per_kwh",
        "adders.climate_env_per_kwh",
        "adders.fuel_adjustment_per_kwh",
        "power_fund_rate",
    ]:
        assert expected in unverified, f"{expected}가 미확인 목록에 없다"

    assert "vat_rate" not in unverified
