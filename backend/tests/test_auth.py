from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.user import User

client = TestClient(app)


def _delete_user(username):
    db = SessionLocal()
    try:
        db.query(User).filter(User.username == username).delete()
        db.commit()
    finally:
        db.close()


def test_login_success():
    response = client.post("/auth/login", data={"username": "viewer1", "password": "viewer123"})

    assert response.status_code == 200

    body = response.json()

    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password():
    response = client.post("/auth/login", data={"username": "viewer1", "password": "wrongpassword"})

    assert response.status_code == 401


def test_login_unknown_user():
    response = client.post("/auth/login", data={"username": "nobody", "password": "whatever"})

    assert response.status_code == 401


def test_me_returns_current_identity(operator_headers):
    response = client.get("/auth/me", headers=operator_headers)

    assert response.status_code == 200
    assert response.json()["username"] == "operator1"
    assert response.json()["role"] == "operator"


def test_me_requires_auth():
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_non_admin_cannot_list_users(viewer_headers):
    response = client.get("/auth/users", headers=viewer_headers)

    assert response.status_code == 403


def test_non_admin_cannot_create_user(operator_headers):
    response = client.post(
        "/auth/users",
        json={"username": "sneaky", "password": "password123", "role": "admin"},
        headers=operator_headers,
    )

    assert response.status_code == 403


def test_admin_can_create_and_list_users(admin_headers):
    _delete_user("test_new_viewer")

    response = client.post(
        "/auth/users",
        json={"username": "test_new_viewer", "password": "password123", "role": "viewer"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["username"] == "test_new_viewer"
    assert response.json()["role"] == "viewer"

    response = client.get("/auth/users", headers=admin_headers)

    assert response.status_code == 200
    assert any(u["username"] == "test_new_viewer" for u in response.json())


def test_duplicate_username_rejected(admin_headers):
    response = client.post(
        "/auth/users",
        json={"username": "viewer1", "password": "password123", "role": "viewer"},
        headers=admin_headers,
    )

    assert response.status_code == 409


def test_invalid_role_rejected(admin_headers):
    response = client.post(
        "/auth/users",
        json={"username": "someone_new", "password": "password123", "role": "superuser"},
        headers=admin_headers,
    )

    assert response.status_code == 422
