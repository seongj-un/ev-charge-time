from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..domain.errors import DomainError, TariffConfigError


def register_error_handlers(app: FastAPI) -> None:
    """도메인 예외를 HTTP로 옮긴다.

    도메인은 HTTP를 모르고, 라우터는 예외를 잡지 않는다. 변환 규칙이
    한 곳에만 있어야 응답 형식이 엔드포인트마다 갈라지지 않는다.
    """

    @app.exception_handler(TariffConfigError)
    def _tariff_config_error(request: Request, exc: TariffConfigError) -> JSONResponse:
        # 설정 파일이 잘못된 것은 서버 잘못이지 요청 잘못이 아니다
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        # 업무 오류는 422 + detail 문자열 (API 명세서 1장)
        return JSONResponse(status_code=422, content={"detail": str(exc)})
