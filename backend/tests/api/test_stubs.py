import pytest

# API 명세서에 있으나 이번 단계에서 구현하지 않는 경로.
# 스키마는 확정하고 본문만 501 — 프론트가 /docs를 보고 먼저 붙을 수 있게.
#
# (메서드, 호출 URL, OpenAPI 경로 템플릿, 유효한 요청 본문)
# 본문이 필요한 엔드포인트에 유효한 값을 주는 이유: 검증은 핸들러보다 먼저
# 돌기 때문에, 빈 본문을 보내면 501이 아니라 422를 보게 되어 스텁이
# 제대로 달렸는지 확인할 수 없다.
#
# 차량(vehicles) 엔드포인트는 F-12로 구현되어 더 이상 스텁이 아니다
# (tests/api/test_vehicles.py 참고). 주변 충전소도 F-07로 구현됐다
# (tests/api/test_chargers.py 참고). 태양광 발전 예측도 F-09로 구현됐다
# (tests/api/test_solar_forecast.py 참고). OpenAPI 등록 확인만 아래에서 계속한다.
#
# 여기에 남은 스텁만 실제로 호출한다는 점이 중요하다 — 구현된 엔드포인트를
# 이 목록에 남겨 두면, 개발자 .env에 키가 있을 때 테스트가 진짜 공공 API를
# 부르게 된다.
STUB_ENDPOINTS = [
    ("POST", "/api/chat", "/api/chat", {"message": "내일 출근 전까지 80% 채우려면?"}),
]

IMPLEMENTED = [
    "/health",
    "/api/timeline",
    "/api/recommend",
    "/api/auth/signup",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/me",
    "/api/me/vehicles",
    "/api/me/vehicles/{vehicle_id}",
    "/api/me/plans",
    "/api/me/plans/summary",
    "/api/me/plans/{plan_id}",
    "/api/chargers",
    "/api/solar-forecast",
]


@pytest.mark.parametrize(
    "method,url,body",
    [(m, u, b) for m, u, _, b in STUB_ENDPOINTS],
    ids=[f"{m} {t}" for m, _, t, _ in STUB_ENDPOINTS],
)
def test_stub_returns_not_implemented(client, method, url, body):
    response = client.request(method, url, json=body)

    assert response.status_code == 501, f"{method} {url} → {response.text}"
    assert isinstance(response.json()["detail"], str)


def test_openapi_declares_every_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]

    for method, _url, template, _body in STUB_ENDPOINTS:
        assert template in paths, f"{template}가 OpenAPI에 없다"
        assert method.lower() in paths[template], f"{method} {template}가 OpenAPI에 없다"

    for route in IMPLEMENTED:
        assert route in paths
