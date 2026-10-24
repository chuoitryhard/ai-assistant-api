from fastapi.testclient import TestClient

from labs.solution import app, config


def test_solution():
    app.dependency_overrides[config] = lambda: {"delay": 0}
    try:
        with TestClient(app) as client:
            assert client.post("/stream", json={"question": " "}).status_code == 422
            assert client.post("/stream", json={"question": "hi", "extra": 1}).status_code == 422
            result = client.post("/stream", json={"question": "hello FastAPI"})
            assert result.text.count("event: token") == 2
            assert "event: done" in result.text
    finally:
        app.dependency_overrides.clear()
