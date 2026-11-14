import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError

from ..domain.errors import DomainError, TariffConfigError

logger = logging.getLogger(__name__)

# 설정 파일 오류의 응답 문구. 예외 문구(파일 경로 포함)는 로그에만 남긴다.
CONFIG_ERROR_DETAILS = {
    "tariff": "요금 설정을 읽지 못했습니다.",
    "holidays": "공휴일 설정을 읽지 못했습니다.",
    "public_prices": "공공 충전 단가 설정을 읽지 못했습니다.",
}
CONFIG_ERROR_FALLBACK = "서버 설정을 읽지 못했습니다."


def register_error_handlers(app: FastAPI) -> None:
    """도메인 예외를 HTTP로 옮긴다.

    도메인은 HTTP를 모르고, 라우터는 예외를 잡지 않는다. 변환 규칙이
    한 곳에만 있어야 응답 형식이 엔드포인트마다 갈라지지 않는다.
    """

    @app.exception_handler(TariffConfigError)
    def _tariff_config_error(request: Request, exc: TariffConfigError) -> JSONResponse:
        # 설정 파일이 잘못된 것은 서버 잘못이지 요청 잘못이 아니다. 예외 문구에는 서버
        # 경로가 들어 있어 운영자만 보도록 로그에 남기고, 응답에는 일반 문구를 쓴다.
        logger.error("설정 파일 오류 (%s): %s", exc.source, exc)
        detail = CONFIG_ERROR_DETAILS.get(exc.source, CONFIG_ERROR_FALLBACK)
        return JSONResponse(status_code=500, content={"detail": detail})

    @app.exception_handler(DomainError)
    def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        # 업무 오류는 422 + detail 문자열 (API 명세서 1장)
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        """DB 제약 위반에 대한 안전망(A-1).

        동시 요청이 DB 제약(유니크 인덱스 등)에 부딪히는 경로가 라우터마다
        하나씩 새로 발견됐다(즐겨찾기 PUT, 기본 차량 동시 설정, 회원가입 이메일
        중복). 개별 라우터가 이미 그 경로를 의미 있게 처리하는 곳(예: 회원가입의
        409)은 이 핸들러에 닿기 전에 자체 HTTPException을 먼저 던지므로 그대로
        유지된다. 이 핸들러는 아직 개별 처리가 없는 경로가 500으로 새는 것을
        막는 마지막 안전망일 뿐, 1차 처리기가 아니다.

        제약 이름 등 내부 스키마 정보는 응답에 담지 않고 서버 로그에만 남긴다.
        """
        logger.warning("처리되지 않은 IntegrityError: %s", exc, exc_info=exc)
        return JSONResponse(
            status_code=409,
            content={"detail": "요청이 기존 데이터와 충돌합니다. 잠시 후 다시 시도하세요."},
        )

    @app.exception_handler(DataError)
    def _data_error(request: Request, exc: DataError) -> JSONResponse:
        """DB 컬럼 제약(길이 초과 등)에 대한 안전망(I-2). IntegrityError(A-1)의
        형제뻘이지만 SQLAlchemy 계층에서는 별개 예외라(둘 다 DatabaseError의
        서로 다른 자식) A-1이 이 경로를 덮지 못했다.

        스키마의 max_length가 1차 방어선이라(schemas.py) 정상 경로에서는
        여기까지 오지 않아야 한다 — 여기는 스키마와 컬럼 정의가 어긋나거나
        새 입력 경로가 max_length를 빠뜨렸을 때를 위한 2차 그물이다.

        상태 코드는 IntegrityError(409, "기존 데이터와 충돌")와 다르게 422를
        쓴다 — 길이 초과는 자원 충돌이 아니라 "요청 값 자체가 잘못됨"이라
        도메인 업무 오류(422 + detail 문자열)와 성격이 같다.
        """
        logger.warning("처리되지 않은 DataError: %s", exc, exc_info=exc)
        return JSONResponse(
            status_code=422,
            content={"detail": "요청 값이 올바르지 않습니다."},
        )
