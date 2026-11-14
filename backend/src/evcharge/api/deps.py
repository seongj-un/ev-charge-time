from functools import lru_cache

from ..domain.calendar import YamlHolidayProvider
from ..domain.public_prices import PublicPrices
from ..domain.tariff import Tariff
from ..settings import get_settings


@lru_cache(maxsize=1)
def get_tariff() -> Tariff:
    return Tariff.load(get_settings().tariff_path)


@lru_cache(maxsize=1)
def get_holidays() -> YamlHolidayProvider:
    return YamlHolidayProvider.load(get_settings().holidays_path)


@lru_cache(maxsize=1)
def get_public_prices() -> PublicPrices:
    return PublicPrices.load(get_settings().public_prices_path)
