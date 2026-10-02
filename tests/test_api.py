import io
import json
from uuid import uuid4

import pytest
from pypdf import PdfWriter

from app.dependencies import get_provider, require_owner
from tests.conftest import upload_txt, wait_document


def test_health_and_ui(client):
    assert client.get("/health").json()["worker_running"] is True
    assert "StudyGateway" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200


def test_openapi_contract(client):
    spec = client.get("/openapi.json").json()
    assert spec["components"]["schemas"]["ChatRequest"]["additionalProperties"] is False
    op = spec["paths"]["/api/v1/chat/stream"]["post"]
    assert "text/event-stream" in op["responses"]["200"]["content"]
    assert op["security"] == [{"APIKeyHeader": []}]
    assert spec["paths"]["/api/v1/documents"]["post"]["responses"]["202"]


@pytest.mark.parametrize("key", ["", "wrong-key"])
def test_auth(client, key):
    response = client.get("/api/v1/documents", headers={"X-API-Key": key})
    assert response.status_code == 401
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "payload",
    [
        {"question": " "},
        {"question": 12},
        {"question": "x" * 4001},
        {"question": "hello", "max_tokens": "512"},
        {"question": "hello", "max_tokens": 0},
        {"question": "hello", "temperature": 2.0},
        {"question": "hello", "extra": True},
        {"question": "hello", "document_ids": ["not-a-uuid"]},
    ],
)
def test_validation(client, payload):
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_dependency_override(client):
    client.app.dependency_overrides[require_owner] = lambda: "test-owner"
    try:
        assert client.get("/api/v1/documents", headers={"X-API-Key": "wrong"}).status_code == 200
    finally:
        client.app.dependency_overrides.clear()


def test_chat_json_and_stream(client):
    response = client.post("/api/v1/chat", json={"question": "Explain async"})
    assert response.json()["provider"] == "demo"
    response = client.post("/api/v1/chat/stream", json={"question": "Explain async"})
    assert response.headers["content-type"].startswith("text/event-stream")
    blocks = response.text.strip().split("\n\n")
    assert blocks[0].startswith("event: meta")
    assert blocks[-1].startswith("event: done")
    tokens = [json.loads(b.split("data: ")[1])["text"] for b in blocks if b.startswith("event: token")]
    assert len(tokens) > 5
    assert "DEMO" in "".join(tokens)
    assert client.app.state.active_streams == 0


def test_document_lifecycle_and_context(client):
    doc = upload_txt(client)
    doc_id = doc["id"]
    assert doc["char_count"] > 10
    body = {"question": "Pydantic là gì?", "document_ids": [doc_id]}
    result = client.post("/api/v1/chat", json=body).json()
    assert result["sources"][0]["document_id"] == doc_id
    assert result["sources"][0]["unit"] == 1
    assert len(client.get("/api/v1/documents").json()["items"]) == 1
    other = client.get(f"/api/v1/documents/{doc_id}", headers={"X-API-Key": "other-key"})
    assert other.status_code == 404
    assert client.post("/api/v1/chat", json=body, headers={"X-API-Key": "other-key"}).status_code == 404
    assert client.delete(f"/api/v1/documents/{doc_id}").status_code == 204
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404


def test_summarize_requires_document(client):
    assert client.post("/api/v1/chat", json={"question": "Tóm tắt", "task": "summarize"}).status_code == 422
    doc = upload_txt(client)
    assert (
        client.post(
            "/api/v1/chat", json={"question": "Tóm tắt", "task": "summarize", "document_ids": [doc["id"]]}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "name, data, status",
    [
        ("virus.exe", b"123", 415),
        ("fake.pdf", b"not a PDF", 415),
        ("fake.pptx", b"not a ZIP", 415),
        ("empty.txt", b"", 422),
    ],
)
def test_upload_rejection(client, name, data, status):
    response = client.post("/api/v1/documents", files={"file": (name, data)})
    assert response.status_code == status
    assert not list(client.app.state.settings.data_dir.joinpath("uploads").iterdir())


def test_large_file(client):
    client.app.state.settings.max_upload_bytes = 1024
    response = client.post("/api/v1/documents", files={"file": ("large.txt", b"a" * 1025)})
    assert response.status_code == 413


def test_document_limit(client):
    client.app.state.settings.max_documents = 1
    upload_txt(client)
    response = client.post("/api/v1/documents", files={"file": ("second.txt", b"abc")})
    assert response.status_code == 429


def test_failed_retry(client):
    response = client.post("/api/v1/documents", files={"file": ("invalid.txt", b"\xff\xfe")})
    doc_id = response.json()["id"]
    assert wait_document(client, doc_id)["status"] == "failed"
    assert client.post(f"/api/v1/documents/{doc_id}/retry").status_code == 202
    assert wait_document(client, doc_id)["status"] == "failed"
    assert client.delete(f"/api/v1/documents/{doc_id}").status_code == 204


def test_ready_retry_invalid_state(client):
    doc = upload_txt(client)
    assert client.post(f"/api/v1/documents/{doc['id']}/retry").status_code == 409


def test_missing_document(client):
    assert client.get(f"/api/v1/documents/{uuid4()}").status_code == 404


def test_blank_pdf_reports_ocr_limit(client):
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=400)
    buffer = io.BytesIO()
    writer.write(buffer)
    response = client.post(
        "/api/v1/documents", files={"file": ("scan.pdf", buffer.getvalue(), "application/pdf")}
    )
    doc = wait_document(client, response.json()["id"])
    assert doc["status"] == "failed"
    assert "OCR" in doc["error"]


def test_stream_post_header_error(client):
    from app.errors import AppError

    class Broken:
        async def stream(self, *_):
            yield "first"
            raise AppError(502, "upstream_incomplete", "stream interrupted")

    client.app.dependency_overrides[get_provider] = lambda: Broken()
    try:
        response = client.post("/api/v1/chat/stream", json={"question": "hello"})
        assert response.status_code == 200
        assert "event: error" in response.text
        assert "event: done" not in response.text
        assert client.app.state.active_streams == 0
    finally:
        client.app.dependency_overrides.clear()


def test_stream_limit(client):
    client.app.state.active_streams = client.app.state.settings.max_active_streams
    try:
        assert client.post("/api/v1/chat/stream", json={"question": "hi"}).status_code == 429
    finally:
        client.app.state.active_streams = 0


def test_oversized_first_chunk_rejected(client):
    class Oversized:
        async def stream(self, *_):
            yield "x" * 60_001

    client.app.dependency_overrides[get_provider] = lambda: Oversized()
    try:
        response = client.post("/api/v1/chat/stream", json={"question": "hello"})
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "output_limit"
        assert client.app.state.active_streams == 0
    finally:
        client.app.dependency_overrides.clear()
