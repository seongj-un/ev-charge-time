from fastapi import APIRouter

from ..deps import get_tariff
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        unverified_tariff_items=get_tariff().unverified_items(),
    )
