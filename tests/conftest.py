import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, api_keys=("test-key", "other-key"), demo_delay=0)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        client.headers["X-API-Key"] = "test-key"
        yield client


def wait_document(client, doc_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = client.get(f"/api/v1/documents/{doc_id}").json()
        if result["status"] in {"ready", "failed"}:
            return result
        time.sleep(0.03)
    raise AssertionError("Extraction worker timed out")


def upload_txt(client, text="FastAPI supports Pydantic validation and async I/O."):
    response = client.post("/api/v1/documents", files={"file": ("lesson.txt", text.encode(), "text/plain")})
    assert response.status_code == 202
    doc = wait_document(client, response.json()["id"])
    assert doc["status"] == "ready", doc
    return doc
