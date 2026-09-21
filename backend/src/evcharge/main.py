from fastapi import FastAPI

from .api.errors import register_error_handlers
from .api.routes import (
    auth,
    chargers,
    extensions,
    health,
    me,
    me_favorites,
    recommend,
    timeline,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="EV 충전 최적 시간 추천 API",
        version="0.1.0",
        description="2026년 개편 전기요금 기준 최저 비용 충전 시간 추천",
    )

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(timeline.router)
    app.include_router(recommend.router)

    # 계약만 확정된 스텁 (501). 프론트가 /docs를 보고 먼저 붙을 수 있게 한다.
    app.include_router(chargers.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(me_favorites.router)
    app.include_router(extensions.router)

    return app


app = create_app()
