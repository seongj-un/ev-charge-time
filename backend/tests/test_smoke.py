from fastapi.testclient import TestClient

from evcharge.main import create_app
from evcharge.settings import Settings


def test_app_starts_and_health_responds():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200


def test_service_key_normalizes_encoding_and_decoding_forms():
    """공공데이터포털이 주는 두 형태의 "일반 인증키"가 같은 값이 되어야 한다.

    포털은 같은 키를 Encoding(%2B…)과 Decoding(+…)으로 나눠 보여준다. httpx가
    쿼리 파라미터를 다시 퍼센트 인코딩하므로 Encoding 키를 그대로 실으면
    %2B → %252B 가 되어 인증이 실패한다. 어느 쪽을 넣어도 되게 해두지 않으면
    "키를 넣었는데 인증이 안 된다"는 상황이 반복된다.
    """
    from evcharge.settings import Settings

    encoding_form = Settings(charger_api_key="abc%2Bdef%2Fghi%3D").charger_api_key
    decoding_form = Settings(charger_api_key="abc+def/ghi=").charger_api_key
    with_noise = Settings(charger_api_key='  "abc+def/ghi="  ').charger_api_key

    assert encoding_form == decoding_form == with_noise == "abc+def/ghi="


def test_missing_service_key_is_empty_not_an_error():
    """키가 없어도 기동은 막지 않는다 — 나머지 기능은 그대로 돌아야 한다."""
    from evcharge.settings import Settings

    assert Settings(charger_api_key="").charger_api_key == ""


# ── DB 주소를 비밀번호 조각으로부터 만든다 ─────────────────────────────────────
#
# 배포 compose가 비밀번호를 URL 문자열에 그대로 끼워 넣었다. 배포 안내가 권하는
# `openssl rand -base64 24`는 `/`·`+`를 낼 수 있고, `@`·`:`·`/`가 들어가면 URL이
# 엉뚱하게 갈린다. 조각(POSTGRES_*)으로 받아 앱이 인코딩한다.

TRICKY_PASSWORD = "p@ss:w/rd%41+x?y#z"


def test_database_url_is_built_from_parts_with_the_password_encoded(monkeypatch):
    from sqlalchemy.engine import make_url

    # conftest가 세션 내내 DATABASE_URL을 테스트 DB로 돌려 둔다. 그게 있으면
    # (의도대로) 그쪽이 이기므로, 조각에서 만드는 경로를 보려면 지운다.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(
        _env_file=None,
        postgres_user="evcharge",
        postgres_password=TRICKY_PASSWORD,
        postgres_host="db",
        postgres_db="evcharge",
    )

    url = make_url(settings.database_url)
    assert url.password == TRICKY_PASSWORD
    assert (url.username, url.host, url.port, url.database) == ("evcharge", "db", 5432, "evcharge")
    assert url.drivername == "postgresql+psycopg"


def test_an_explicit_database_url_wins_over_the_parts():
    """테스트(conftest)와 개발은 DATABASE_URL을 직접 준다. 그쪽이 이긴다."""
    explicit = "postgresql+psycopg://a:b@localhost:5432/evcharge_test"

    settings = Settings(_env_file=None, database_url=explicit, postgres_password="other")

    assert settings.database_url == explicit


def test_alembic_ini_escaping_round_trips_a_percent_encoded_url(monkeypatch):
    """alembic Config는 configparser라 `%`를 보간 문법으로 읽는다. 인코딩된 비밀번호
    (`%40` 등)를 그대로 set_main_option에 넣으면 ValueError가 난다."""
    from alembic.config import Config

    from evcharge.settings import alembic_safe_url

    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = Settings(
        _env_file=None, postgres_password=TRICKY_PASSWORD, postgres_host="db"
    ).database_url
    assert "%" in url  # 인코딩된 비밀번호가 실제로 들어 있어야 이 테스트가 의미 있다
    config = Config()

    config.set_main_option("sqlalchemy.url", alembic_safe_url(url))

    assert config.get_main_option("sqlalchemy.url") == url
