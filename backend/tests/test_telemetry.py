from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.telemetry import Telemetry

client = TestClient(app)


def _clear_telemetry(robot_id):
    db = SessionLocal()
    try:
        db.query(Telemetry).filter(Telemetry.robot_id == robot_id).delete()
        db.commit()
    finally:
        db.close()


def _insert_telemetry(robot_id, battery, temperature, x, y):
    db = SessionLocal()
    try:
        row = Telemetry(
            robot_id=robot_id,
            battery=battery,
            temperature=temperature,
            x=x,
            y=y,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def test_telemetry_empty_for_fresh_robot():
    _clear_telemetry("R004")

    response = client.get("/robots/R004/telemetry")

    assert response.status_code == 200
    assert response.json() == []


def test_telemetry_invalid_robot():
    response = client.get("/robots/R999/telemetry")

    assert response.status_code == 404


def test_telemetry_latest_invalid_robot():
    response = client.get("/robots/R999/telemetry/latest")

    assert response.status_code == 404


def test_telemetry_latest_no_readings():
    _clear_telemetry("R005")

    response = client.get("/robots/R005/telemetry/latest")

    assert response.status_code == 404


def test_telemetry_list_returns_inserted_readings():
    _clear_telemetry("R001")
    _insert_telemetry("R001", battery=90.0, temperature=40.0, x=1.0, y=2.0)
    _insert_telemetry("R001", battery=89.5, temperature=40.5, x=1.5, y=2.5)

    response = client.get("/robots/R001/telemetry")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2
    assert all(reading["robot_id"] == "R001" for reading in data)


def test_telemetry_list_respects_limit():
    _clear_telemetry("R002")

    for i in range(5):
        _insert_telemetry("R002", battery=100.0 - i, temperature=35.0, x=0.0, y=0.0)

    response = client.get("/robots/R002/telemetry?limit=2")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_telemetry_list_ordered_most_recent_first():
    _clear_telemetry("R003")
    first_id = _insert_telemetry("R003", battery=95.0, temperature=36.0, x=0.0, y=0.0)
    second_id = _insert_telemetry("R003", battery=94.0, temperature=36.5, x=0.5, y=0.5)

    response = client.get("/robots/R003/telemetry")

    assert response.status_code == 200

    data = response.json()

    assert data[0]["id"] == second_id
    assert data[1]["id"] == first_id


def test_telemetry_latest_returns_most_recent_reading():
    _clear_telemetry("R001")
    _insert_telemetry("R001", battery=90.0, temperature=40.0, x=1.0, y=2.0)
    latest_id = _insert_telemetry("R001", battery=85.0, temperature=41.0, x=2.0, y=3.0)

    response = client.get("/robots/R001/telemetry/latest")

    assert response.status_code == 200

    reading = response.json()

    assert reading["id"] == latest_id
    assert reading["battery"] == 85.0
