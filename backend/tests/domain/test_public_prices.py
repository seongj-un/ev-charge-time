from pathlib import Path

import pytest

from evcharge.domain.errors import TariffConfigError
from evcharge.domain.public_prices import PublicPrices
from evcharge.settings import get_settings

VALID = """
version: "test"
slow:
  value: {member: 293.3, roaming: 397.9, nonmember: 446.0}
  source: "test"
  status: verified
fast:
  value: {member: 358.1, roaming: 418.5, nonmember: 466.5}
  source: "test"
  status: unverified
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "prices.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_shipped_config_loads_with_the_kca_averages():
    prices = PublicPrices.load(get_settings().public_prices_path)

    assert prices.version == "2025.12.17-kca"
    assert prices.for_speed("slow").prices == {
        "member": 293.3,
        "roaming": 397.9,
        "nonmember": 446.0,
    }
    assert prices.for_speed("fast").prices == {
        "member": 358.1,
        "roaming": 418.5,
        "nonmember": 466.5,
    }
    assert prices.for_speed("slow").verified is True
    # 급속 평균은 한 보도에서만 확인했다 (설정 파일 source 참고).
    assert prices.for_speed("fast").verified is False


def test_valid_file_loads(tmp_path):
    prices = PublicPrices.load(write(tmp_path, VALID))

    assert prices.for_speed("fast").price("roaming") == 418.5


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("member: 293.3,", "member: -1,"),
        ("member: 293.3,", "member: 0,"),
        ("member: 293.3,", "member: .nan,"),
        ("member: 293.3,", "member: .inf,"),
        ("member: 293.3,", "member: true,"),
        ("member: 293.3,", "member: \"293\","),
        ("member: 293.3, ", ""),
        ("status: unverified", "status: maybe"),
    ],
)
def test_bad_values_fail_loudly(tmp_path, old, new):
    with pytest.raises(TariffConfigError):
        PublicPrices.load(write(tmp_path, VALID.replace(old, new, 1)))


def test_missing_speed_fails_loudly(tmp_path):
    text = VALID.split("fast:")[0]
    with pytest.raises(TariffConfigError):
        PublicPrices.load(write(tmp_path, text))
