import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _login_token(username, password):
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def viewer_token():
    return _login_token("viewer1", "viewer123")


@pytest.fixture(scope="session")
def operator_token():
    return _login_token("operator1", "operator123")


@pytest.fixture(scope="session")
def admin_token():
    return _login_token("admin1", "admin123")


@pytest.fixture(scope="session")
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest.fixture(scope="session")
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
