"""공공 충전기 결제 방식별 평균 단가 (와트잇 BE-4).

``config/public_charging_prices.yaml``을 ``Tariff`` 로더로 읽고, 값의 모양을
여기서 확인한다. 값이 틀린 설정은 요청 잘못이 아니라 서버 잘못이므로
``TariffConfigError``(→ 500)다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import TariffConfigError
from .tariff import Tariff

Payment = Literal["member", "roaming", "nonmember"]
ChargerSpeed = Literal["slow", "fast"]

PAYMENTS: tuple[Payment, ...] = ("member", "roaming", "nonmember")
SPEEDS: tuple[ChargerSpeed, ...] = ("slow", "fast")


@dataclass(frozen=True)
class SpeedPrices:
    """한 충전 속도의 결제 방식별 평균 단가(원/kWh)와 출처 확인 상태."""

    prices: dict[str, float]
    verified: bool

    def price(self, payment: Payment) -> float:
        return self.prices[payment]


@dataclass(frozen=True)
class PublicPrices:
    version: str
    by_speed: dict[str, SpeedPrices]

    @classmethod
    def load(cls, path: Path) -> PublicPrices:
        tariff = Tariff.load(path, source="public_prices")
        by_speed: dict[str, SpeedPrices] = {}
        for speed in SPEEDS:
            item = tariff.items.get(speed)
            if item is None or not isinstance(item.value, dict):
                raise TariffConfigError(
                    f"공공 충전 단가 설정에 '{speed}' 값이 없습니다.", source="public_prices"
                )
            prices: dict[str, float] = {}
            for payment in PAYMENTS:
                value = item.value.get(payment)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int | float)
                    or not math.isfinite(value)
                    or value <= 0
                ):
                    raise TariffConfigError(
                        f"공공 충전 단가 '{speed}.{payment}'가 양수가 아닙니다: {value!r}",
                        source="public_prices",
                    )
                prices[payment] = float(value)
            by_speed[speed] = SpeedPrices(prices=prices, verified=item.status == "verified")
        return cls(version=tariff.version, by_speed=by_speed)

    def for_speed(self, speed: ChargerSpeed) -> SpeedPrices:
        return self.by_speed[speed]
