import pytest
from fastapi.testclient import TestClient

from backend.app.agent.exceptions import EmbeddingProviderError
from backend.app.main import app
from backend.app.routes.documents import get_embeddings_client

client = TestClient(app)

EMBEDDING_DIM = 1024


class FakeEmbeddingsClient:
    """Deterministic fixed-length vectors — no test here ever calls the
    real Voyage API."""

    def embed(self, texts, *, input_type):
        return [[0.1] * EMBEDDING_DIM for _ in texts]


class RaisingEmbeddingsClient:
    def embed(self, texts, *, input_type):
        raise EmbeddingProviderError("simulated provider outage")


@pytest.fixture(autouse=True)
def _fake_embeddings():
    app.dependency_overrides[get_embeddings_client] = lambda: FakeEmbeddingsClient()
    yield
    del app.dependency_overrides[get_embeddings_client]


def test_upload_document_requires_auth():
    response = client.post("/documents", json={"title": "x", "content": "some content"})

    assert response.status_code == 401


def test_non_admin_cannot_upload(operator_headers):
    response = client.post(
        "/documents",
        json={"title": "Runbook", "content": "How to restart a robot."},
        headers=operator_headers,
    )

    assert response.status_code == 403


def test_admin_can_upload_document(admin_headers):
    response = client.post(
        "/documents",
        json={
            "title": "Overheating Runbook",
            "source": "manual paste",
            "content": "If a robot overheats, stop it and let it cool.",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Overheating Runbook"
    assert data["chunk_count"] >= 1


def test_upload_document_rejects_empty_content(admin_headers):
    response = client.post(
        "/documents",
        json={"title": "Empty", "content": "   "},
        headers=admin_headers,
    )

    assert response.status_code == 400


def test_upload_document_embedding_failure_returns_503(admin_headers):
    app.dependency_overrides[get_embeddings_client] = lambda: RaisingEmbeddingsClient()

    response = client.post(
        "/documents",
        json={"title": "Doomed", "content": "this will fail to embed"},
        headers=admin_headers,
    )

    assert response.status_code == 503


def test_list_documents_any_role(viewer_headers, admin_headers):
    client.post(
        "/documents",
        json={"title": "Listable Doc", "content": "content to list"},
        headers=admin_headers,
    )

    response = client.get("/documents", headers=viewer_headers)

    assert response.status_code == 200
    assert any(d["title"] == "Listable Doc" for d in response.json())


def test_get_unknown_document_404(viewer_headers):
    response = client.get("/documents/999999", headers=viewer_headers)

    assert response.status_code == 404


def test_non_admin_cannot_delete(admin_headers, operator_headers):
    created = client.post(
        "/documents",
        json={"title": "To Delete", "content": "content"},
        headers=admin_headers,
    ).json()

    response = client.delete(f"/documents/{created['id']}", headers=operator_headers)

    assert response.status_code == 403


def test_admin_can_delete_document(admin_headers):
    created = client.post(
        "/documents",
        json={"title": "Deletable", "content": "content"},
        headers=admin_headers,
    ).json()

    response = client.delete(f"/documents/{created['id']}", headers=admin_headers)
    assert response.status_code == 204

    get_response = client.get(f"/documents/{created['id']}", headers=admin_headers)
    assert get_response.status_code == 404
