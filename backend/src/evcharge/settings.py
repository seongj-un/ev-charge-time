from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """환경 변수로 주입되는 설정. 요금 값은 여기가 아니라 config/tariff.yaml에 있다."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://evcharge:evcharge@localhost:5432/evcharge"
    tariff_path: Path = BACKEND_ROOT / "config" / "tariff.yaml"
    holidays_path: Path = BACKEND_ROOT / "config" / "holidays.yaml"


def get_settings() -> Settings:
    return Settings()
