from fastapi import FastAPI

from .api.errors import register_error_handlers
from .api.routes import health, timeline


def create_app() -> FastAPI:
    app = FastAPI(
        title="EV 충전 최적 시간 추천 API",
        version="0.1.0",
        description="2026년 개편 전기요금 기준 최저 비용 충전 시간 추천",
    )

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(timeline.router)

    return app


app = create_app()
