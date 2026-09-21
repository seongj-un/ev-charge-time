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

    # F-10 자연어 질의 — Google Gemini 무료 티어 (https://aistudio.google.com/apikey)
    #
    # `charger_api_key`와 같은 규칙이다: 비어 있으면 POST /api/chat은 501을
    # 반환하고, 나머지 기능은 키 없이도 전부 돌아야 하므로 기동 시점에 막지 않는다.
    #
    # 공공데이터포털 키와 달리 정규화가 필요 없다 — SDK가 이 값을 쿼리
    # 문자열이 아니라 x-goog-api-key 헤더로 실으므로 Encoding/Decoding 구분이
    # 없고, AI Studio가 주는 키에는 `%`가 들어가지 않는다.
    gemini_api_key: str = ""

    # 모델 ID를 설정으로 두는 이유: 무료 티어에서 쓸 수 있는 모델은 바뀐다.
    # 기본값은 설치된 google-genai 2.24.0이 "현재 서비스되는 모델"로 열거한
    # 목록(_gaos/types/interactions/model.py의 Model Literal)에서 확인한 정확한
    # 표기다 — 그 목록의 설명은 "Our most cost-efficient model, optimized for
    # high-volume agentic tasks, translation, and simple data processing".
    # `-preview` 접미사는 붙지 않는다.
    #
    # 키가 없어 models.list()로 이 계정에서 실제로 쓸 수 있는지까지는 확인하지
    # 못했다. 거부되면 이 값만 바꾸면 된다 (.env.example에 후보를 적어 뒀다).
    gemini_model: str = "gemini-3.1-flash-lite"

    # 사용자별 호출 제한 (명세 F-10, 초과 시 429).
    #
    # 20회/시간으로 잡은 근거:
    #  - 무료 티어는 분당·일일 호출 한도가 프로젝트 전체에 걸린다. 한 사람이
    #    그 공용 예산을 다 써버리면 시연 중 다른 심사위원의 질문이 전부 막힌다.
    #  - 실제 사용은 "질문 몇 개"다. 질문 하나당 모델 호출은 정확히 1회이므로
    #    (문장은 서버가 쓴다 — api/chat_service.py) 20회/시간은 정상 사용자가
    #    체감할 일이 없으면서, 폭주하는 클라이언트 하나가 예산을 비우는 것은 막는다.
    #  - 고정 창(fixed window)이라 경계에서 최대 2배까지 몰릴 수 있다. 정확한
    #    슬라이딩 윈도우가 필요할 만큼 비싼 자원은 아니라 단순한 쪽을 택했다.
    chat_rate_limit_count: int = 20
    chat_rate_limit_window_minutes: int = 60

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
