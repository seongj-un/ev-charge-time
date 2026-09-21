import pytest
from fastapi.testclient import TestClient

from evcharge.main import create_app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(create_app())
