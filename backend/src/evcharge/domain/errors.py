class DomainError(Exception):
    """도메인 계층의 모든 예외. api/errors.py가 이것을 HTTP로 변환한다."""


class TariffConfigError(DomainError):
    """설정 파일(요금, 공휴일, 공공 충전 단가) 자체가 잘못됐다.

    문구에는 파일 경로가 들어갈 수 있어 로그에만 쓴다. 응답에는 ``source``에 맞는 일반
    문구를 쓴다(``api/errors.py``).
    """

    def __init__(self, message: str, *, source: str = "tariff") -> None:
        super().__init__(message)
        # "tariff" | "holidays" | "public_prices"
        self.source = source


class TariffNotConfiguredError(DomainError):
    """계산에 필요한 요금 값이 설정에 없다."""


class InsufficientTimeError(DomainError):
    """충전에 필요한 시간이 가능한 시간보다 길다."""


class InvalidPriceError(DomainError):
    """입력한 단가로는 계산할 수 없다 (예: 할인액보다 낮은 공공 급속 단가)."""


class HolidayDataMissingError(DomainError):
    """그 연도의 공휴일 목록이 없어 요금 구간을 판정할 수 없다."""
