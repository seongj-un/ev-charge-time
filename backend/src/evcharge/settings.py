from pathlib import Path

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
    # 키는 반드시 **Decoding** 키를 넣는다. httpx가 쿼리 파라미터를 알아서
    # 인코딩하므로 Encoding 키를 넣으면 '%2B'가 두 번 인코딩돼 인증이 실패한다
    # (SERVICE_KEY_IS_NOT_REGISTERED_ERROR). 신청 직후 활성화에 1시간쯤
    # 걸리는 경우가 있다.
    #
    # 비어 있으면 GET /api/chargers 는 지금처럼 501을 반환한다 — 키 없이도
    # 나머지 기능은 그대로 돌아야 하므로 기동 시점에 막지 않는다.
    charger_api_key: str = ""

    # 수집 대상 시도 코드(행정구역코드 앞 2자리). 개발계정 트래픽이 하루
    # 1,000건이라 전국 17개 시도를 다 받으면 넘친다. 빛가람(나주) 대회이므로
    # 전남(46)·광주(29)만 받는다. 쉼표로 구분한다.
    charger_zcodes: str = "46,29"



def get_settings() -> Settings:
    return Settings()
