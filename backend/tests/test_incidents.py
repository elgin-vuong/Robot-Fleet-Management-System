from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _create_incident(headers, robot_id="R001", severity="high", title="Overheating detected"):
    return client.post(
        "/incidents",
        json={
            "robot_id": robot_id,
            "title": title,
            "description": "Temperature exceeded safe threshold.",
            "severity": severity,
        },
        headers=headers,
    )


def test_report_incident_requires_auth():
    response = client.post(
        "/incidents",
        json={"robot_id": "R001", "title": "x", "description": "x", "severity": "low"},
    )

    assert response.status_code == 401


def test_viewer_cannot_report_incident(viewer_headers):
    response = _create_incident(viewer_headers)

    assert response.status_code == 403


def test_operator_can_report_incident(operator_headers):
    response = _create_incident(operator_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["robot_id"] == "R001"
    assert data["status"] == "open"
    assert data["resolved_at"] is None


def test_report_incident_invalid_severity(operator_headers):
    response = _create_incident(operator_headers, severity="apocalyptic")

    assert response.status_code == 422


def test_report_incident_unknown_robot(operator_headers):
    response = _create_incident(operator_headers, robot_id="R999")

    assert response.status_code == 404


def test_list_incidents_any_role(viewer_headers, operator_headers):
    _create_incident(operator_headers, robot_id="R002")

    response = client.get("/incidents", params={"robot_id": "R002"}, headers=viewer_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert all(item["robot_id"] == "R002" for item in data)


def test_get_single_incident(operator_headers):
    created = _create_incident(operator_headers, robot_id="R003").json()

    response = client.get(f"/incidents/{created['id']}", headers=operator_headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_incident_404(viewer_headers):
    response = client.get("/incidents/999999", headers=viewer_headers)

    assert response.status_code == 404


def test_viewer_cannot_resolve_incident(operator_headers, viewer_headers):
    created = _create_incident(operator_headers, robot_id="R004").json()

    response = client.post(
        f"/incidents/{created['id']}/resolve",
        json={"resolution_notes": "fixed"},
        headers=viewer_headers,
    )

    assert response.status_code == 403


def test_resolve_incident(operator_headers):
    created = _create_incident(operator_headers, robot_id="R005").json()

    response = client.post(
        f"/incidents/{created['id']}/resolve",
        json={"resolution_notes": "Replaced cooling fan."},
        headers=operator_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resolved"
    assert data["resolved_at"] is not None
    assert data["resolution_notes"] == "Replaced cooling fan."


def test_resolve_already_resolved_incident_conflicts(operator_headers):
    created = _create_incident(operator_headers, robot_id="R001").json()
    client.post(f"/incidents/{created['id']}/resolve", json={}, headers=operator_headers)

    response = client.post(f"/incidents/{created['id']}/resolve", json={}, headers=operator_headers)

    assert response.status_code == 409


def test_resolve_unknown_incident_404(operator_headers):
    response = client.post("/incidents/999999/resolve", json={}, headers=operator_headers)

    assert response.status_code == 404
