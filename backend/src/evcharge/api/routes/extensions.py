from datetime import date
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query

from ...infra.kma_api import KmaApiClient
from ...settings import get_settings
from ..schemas import ChatRequest, ChatResponse, SolarForecast
from ..solar_service import SolarForecastService, parse_capacities
from ._stub import not_implemented

router = APIRouter(prefix="/api", tags=["extensions"])


def kma_api_key() -> str:
    """설정의 기상청 인증키.

    의존성으로 빼 둔 이유는 ``routes/chargers.py``와 같다 — 테스트가
    ``dependency_overrides``로 "키 있음/없음"을 직접 정할 수 있어야 한다.
    개발자 ``.env``에 키가 있느냐에 따라 테스트 결과가 갈리면 안 된다.
    """
    return get_settings().kma_api_key


@lru_cache(maxsize=1)
def get_solar_service() -> SolarForecastService:
    """예보 서비스. **싱글턴이어야 한다** — 캐시가 요청 사이에 살아남아야
    하기 때문이다. 예보는 하루 여덟 번만 갱신되는데 요청마다 부르면
    일일 할당량을 낭비한다. ``deps.py``의 ``get_tariff``와 같은 방식이다.
    """
    settings = get_settings()
    return SolarForecastService(
        client=KmaApiClient(service_key=settings.kma_api_key),
        capacities=parse_capacities(settings.solar_capacity_mw),
        capacity_source=settings.solar_capacity_source,
    )


@router.get("/solar-forecast", response_model=SolarForecast)
def solar_forecast(
    region: str = Query(
        max_length=32,
        description="시도 이름. 대회 지역은 '전남'·'나주'·'빛가람' 모두 같은 격자를 가리킨다.",
    ),
    day: date = Query(description="예측할 날짜. 기상청 시간별 예보는 약 2일 앞까지만 있다."),
    api_key: str = Depends(kma_api_key),
    service: SolarForecastService = Depends(get_solar_service),
) -> SolarForecast:
    """F-09 태양광 발전 예측 (확장).

    기상청 단기예보(하늘상태·강수형태)로 맑은날 일사량을 깎는 물리 근사다.
    계산식과 근거는 ``domain/solar.py``, 응답 필드의 판단(특히
    ``predicted_mwh``가 왜 비어 있을 수 있는지)은 ``api/solar_service.py``에 있다.
    """
    if not api_key:
        # 키가 없으면 예보를 받을 방법 자체가 없다. settings.py가 약속한 대로
        # 501을 유지한다 — 프론트가 "아직 열리지 않았어요"로 안내한다.
        raise HTTPException(
            status_code=501,
            detail="태양광 발전 예측은 아직 준비되지 않았습니다. (기상청 API 인증키 미설정)",
        )

    return service.forecast(region, day)


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    """F-10 자연어 질의 (확장). 사용자별 호출 제한, 초과 시 429."""
    return not_implemented("자연어 질의")()
