from datetime import date

from fastapi import APIRouter

from ..schemas import ChatRequest, ChatResponse, SolarForecast
from ._stub import not_implemented

router = APIRouter(prefix="/api", tags=["extensions"])


@router.get("/solar-forecast", response_model=SolarForecast)
def solar_forecast(region: str, day: date):
    """F-09 태양광 발전 예측 (확장). 기상청 단기예보 + 전력거래소 발전량."""
    return not_implemented("태양광 발전 예측")()


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    """F-10 자연어 질의 (확장). 사용자별 호출 제한, 초과 시 429."""
    return not_implemented("자연어 질의")()
