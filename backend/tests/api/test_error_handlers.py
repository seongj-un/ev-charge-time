"""errors.py의 DataError 안전망(I-2 2차 그물) 단위 테스트.

스키마의 max_length가 1차 방어선이다(test_auth.py::test_signup_*_over_column_
length_is_422, test_vehicles.py::test_create_vehicle_name_over_column_length_
is_422, test_favorites.py::test_put_favorite_station_id_over_column_length_
is_422 참고) — 정상 입력 경로로는 이 핸들러까지 닿지 않는다. 이 파일은
스키마가 놓친 경로나 앞으로 생길 새 DataError 발생 지점도 500이 아니라
422로 막힌다는 것을, 핸들러 자체를 직접 트리거해서 확인한다.

(Finding 2와 달리 여기서는 합성 앱이 적절하다 — 검증 대상이 "라우터가
주입된 response 객체를 잃지 않는가"처럼 특정 라우터 코드의 동작이 아니라
"예외 → HTTP 변환 규칙 자체가 옳은가"이므로, 실제 라우터를 거칠 필요가
없다. A-1의 IntegrityError 안전망도 같은 성격이지만 그쪽은 진짜 동시
경쟁(test_vehicles.py의 concurrent 픽스처)으로 자연스럽게 재현되는 반면,
DataError는 스키마 갭을 일부러 남겨두지 않는 한 살아있는 엔드포인트로
재현할 경로가 없어 여기서 직접 검증한다.)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError

from evcharge.api.errors import register_error_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def _boom():
        raise DataError(
            "INSERT INTO users (nickname) VALUES (%(nickname)s)",
            {"nickname": "n" * 60},
            Exception("value too long for type character varying(50)"),
        )

    return app


def test_data_error_is_mapped_to_422_not_500():
    client = TestClient(_make_app(), raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
