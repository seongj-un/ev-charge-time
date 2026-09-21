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


def test_real_config_unverified_set_is_exactly_what_we_expect():
    """실제 설정의 미확인 항목 집합을 통째로 고정한다.

    항목 하나가 verified로 바뀌거나 반대로 풀리면 이 테스트가 깨진다 — 요금
    설정의 상태 변경은 항상 의도적이어야 하고, 조용히 일어나면 안 된다.
    (/health와 /api/recommend가 이 목록을 그대로 내보내므로 화면의 "요금 일부
    확인 중" 안내가 여기에 달려 있다.)

    한전 공식 요금표(2023-11-09)를 확보해 시간대·전력량요금·가산항목·세금은
    verified가 됐다. 남은 셋은 그 문서가 정하지 않는 값들이다:
    공공 급속 단가는 충전사업자가 정하고, EV 충전 특례할인은 별도 고시다.
    """
    from evcharge.settings import get_settings

    unverified = Tariff.load(get_settings().tariff_path).unverified_items()

    assert set(unverified) == {
        "public_fast.base_price_per_kwh",
        "public_fast.weekend_discount",
        "weekend_discount_self",
    }


def test_real_config_marks_the_kepco_sourced_items_verified():
    """공식 요금표에서 옮긴 항목은 미확인 목록에 없어야 한다.

    누가 값을 잠정치로 되돌리면서 status만 verified로 남겨두는 실수는 위
    테스트가 못 잡는다. 반대로 status를 되돌리면 이 테스트가 잡는다.
    """
    from evcharge.settings import get_settings

    unverified = Tariff.load(get_settings().tariff_path).unverified_items()

    for kepco_sourced in [
        "time_bands",
        "seasons",
        "energy_charge.self_low",
        "energy_charge.self_high",
        "adders.climate_env_per_kwh",
        "adders.fuel_adjustment_per_kwh",
        "vat_rate",
        "power_fund_rate",
    ]:
        assert kepco_sourced not in unverified, f"{kepco_sourced}가 미확인으로 남아있다"
