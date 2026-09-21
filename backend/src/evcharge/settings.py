from pathlib import Path
from urllib.parse import unquote

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """환경 변수로 주입되는 설정. 요금 값은 여기가 아니라 config/tariff.yaml에 있다."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://evcharge:evcharge@localhost:5432/evcharge"
    tariff_path: Path = BACKEND_ROOT / "config" / "tariff.yaml"
    holidays_path: Path = BACKEND_ROOT / "config" / "holidays.yaml"

    # 인증 (infra/security.py, api/auth_deps.py)
    cookie_secure: bool = False
    session_days: int = 14
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # F-07 주변 충전소 — 공공데이터포털 "한국환경공단_전기자동차 충전소 정보"
    # (https://www.data.go.kr/data/15076352/openapi.do)
    #
    # 포털이 주는 "일반 인증키"를 그대로 넣으면 된다. Encoding·Decoding 어느
    # 쪽을 넣어도 동작한다 — 아래 validator가 정규화한다. 둘은 같은 키를 달리
    # 표기한 것뿐인데, 사람이 매번 어느 쪽인지 신경 쓰게 만들 이유가 없다.
    # (이 API를 붙이는 사람 대부분이 한 번은 여기서 걸린다.)
    #
    # 신청 직후 키 활성화에 1시간쯤 걸리는 경우가 있다.
    #
    # 비어 있으면 GET /api/chargers 는 지금처럼 501을 반환한다 — 키 없이도
    # 나머지 기능은 그대로 돌아야 하므로 기동 시점에 막지 않는다.
    charger_api_key: str = ""

    # 수집 대상 시도 코드. 개발계정 트래픽이 하루 1,000건이라 전국을 다
    # 받으면 넘친다(2026-09 기준 전국 524,903건). 빛가람(나주) 대회이므로
    # 해당 지역만 받는다. 쉼표로 구분한다.
    #
    # 12 = 전남광주통합특별시 (32,835건, 그중 나주 소재 다수).
    # 표준 행정구역코드의 전남(46)·광주(29)로는 0건이 나온다 — 두 지역이
    # 통합되면서 이 API가 12를 쓴다. 실제 응답의 zcode 값을 표본 조사해
    # 확인했다. 같은 이유로 강원은 42가 아니라 51, 전북은 45가 아니라 52다.
    charger_zcodes: str = "12"

    @field_validator("charger_api_key")
    @classmethod
    def _normalize_service_key(cls, value: str) -> str:
        """Encoding 키가 들어와도 Decoding 형태로 맞춰 둔다.

        공공데이터포털은 같은 키를 Encoding(``%2B``…)과 Decoding(``+``…) 두
        형태로 보여준다. httpx가 쿼리 파라미터를 알아서 퍼센트 인코딩하므로
        Encoding 키를 그대로 실으면 ``%2B``의 ``%``가 다시 인코딩돼(``%252B``)
        인증이 실패한다(SERVICE_KEY_IS_NOT_REGISTERED_ERROR).

        ``%``가 보이면 한 번 디코드해 Decoding 형태로 되돌린다. Decoding 키는
        ``%``를 담지 않으므로 그대로 통과한다. 앞뒤 공백·따옴표도 걷어낸다 —
        복사·붙여넣기에서 흔히 딸려 온다.
        """
        cleaned = value.strip().strip('"').strip("'")
        return unquote(cleaned) if "%" in cleaned else cleaned



def get_settings() -> Settings:
    return Settings()
