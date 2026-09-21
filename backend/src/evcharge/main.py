from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="EV 충전 최적 시간 추천 API",
        version="0.1.0",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
