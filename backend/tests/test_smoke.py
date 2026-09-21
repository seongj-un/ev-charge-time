from fastapi.testclient import TestClient

from evcharge.main import create_app


def test_app_starts_and_health_responds():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
