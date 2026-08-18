from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.cache import redis_client
from backend.app.routes.robots import ROBOTS_CACHE_KEY, _robot_cache_key

client = TestClient(app)

def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_robots():
    response = client.get("/robots")

    assert response.status_code == 200

    data = response.json()

    assert len(data) > 0
    assert "id" in data[0]

def test_get_single_robot():
    response = client.get("/robots/R001")

    assert response.status_code == 200

    robot = response.json()

    assert robot["id"] == "R001"

def test_invalid_robot():
    response = client.get("/robots/R823")

    assert response.status_code == 404

def test_start_robot():
    response = client.post(
        "/robots/R001/command",
        json={
            "command": "START"
        }
    )

    assert response.status_code == 200

def test_stop_robot():
    response = client.post(
        "/robots/R001/command",
        json={
            "command": "STOP"
        }
    )
    assert response.status_code == 200

def test_invalid_command():
    response = client.post(
        "/robots/R001/command",
        json={
            "command": "FLY"
        }
    )
    assert response.status_code == 404

def test_start_robot_invalid_id():
    response = client.post(
        "/robots/R999/command",
        json={
            "command": "START"
        }
    )
    assert response.status_code == 404

def test_stop_robot_invalid_id():
    response = client.post(
        "/robots/R999/command",
        json={
            "command": "STOP"
        }
    )
    assert response.status_code == 404

def test_start_robot_valid_id():
    response = client.post(
        "/robots/R003/command",
        json={
            "command": "START"
        }
    )
    assert response.status_code == 200

def test_get_robot_populates_cache():
    redis_client.delete(_robot_cache_key("R004"))

    client.get("/robots/R004")

    assert redis_client.exists(_robot_cache_key("R004"))

def test_get_robots_populates_list_cache():
    redis_client.delete(ROBOTS_CACHE_KEY)

    client.get("/robots")

    assert redis_client.exists(ROBOTS_CACHE_KEY)

def test_command_invalidates_cache():
    client.get("/robots/R004")
    client.get("/robots")

    assert redis_client.exists(_robot_cache_key("R004"))
    assert redis_client.exists(ROBOTS_CACHE_KEY)

    response = client.post(
        "/robots/R004/command",
        json={
            "command": "START"
        }
    )

    assert response.status_code == 200
    assert not redis_client.exists(_robot_cache_key("R004"))
    assert not redis_client.exists(ROBOTS_CACHE_KEY)

