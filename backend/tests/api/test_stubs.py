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
# (tests/api/test_chargers.py 참고). 자연어 질의(/api/chat)도 F-10으로
# 구현됐다 (tests/api/test_chat.py 참고) — 키가 없을 때 501을 내는 것은
# 이제 "스텁"이 아니라 그 엔드포인트의 계약이라, 그쪽 테스트가 검증한다.
# OpenAPI 등록 확인만 아래에서 계속한다.
STUB_ENDPOINTS = [
    ("GET", "/api/solar-forecast?region=전남&day=2026-10-17", "/api/solar-forecast", None),
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
    "/api/chat",
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
