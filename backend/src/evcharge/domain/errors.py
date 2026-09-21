class DomainError(Exception):
    """도메인 계층의 모든 예외. api/errors.py가 이것을 HTTP로 변환한다."""


class TariffConfigError(DomainError):
    """요금 설정 파일 자체가 잘못됐다. 앱 기동 시점에 터뜨린다."""


class TariffNotConfiguredError(DomainError):
    """계산에 필요한 요금 값이 설정에 없다."""


class InsufficientTimeError(DomainError):
    """충전에 필요한 시간이 가능한 시간보다 길다."""
