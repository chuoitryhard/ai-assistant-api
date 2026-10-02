import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.main import create_app
from app.provider import Provider, sse_data
from app.schemas import ChatRequest


@pytest.mark.asyncio
async def test_multiline_sse():
    async def lines():
        for line in [": heartbeat", "event: token", "data: {", 'data: "x": 1}', "", "data: tail"]:
            yield line

    assert [x async for x in sse_data(lines())] == ['{\n"x": 1}', "tail"]


def event(content):
    return "data: " + json.dumps({"choices": [{"delta": {"content": content}}]}) + "\n\n"


def test_upstream_success(settings):
    settings.provider = "openai_compatible"

    def handler(request):
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["max_tokens"] == 512
        return httpx.Response(200, text=event("Xin ") + event("chào") + "data: [DONE]\n\n")

    with TestClient(create_app(settings, transport=httpx.MockTransport(handler))) as client:
        result = client.post("/api/v1/chat", headers={"X-API-Key": "test-key"}, json={"question": "Hi"})
        assert result.status_code == 200
        assert result.json()["answer"] == "Xin chào"


@pytest.mark.parametrize("status", [401, 429, 500])
def test_upstream_http_error(settings, status):
    settings.provider = "openai_compatible"
    with TestClient(
        create_app(settings, transport=httpx.MockTransport(lambda r: httpx.Response(status)))
    ) as client:
        result = client.post(
            "/api/v1/chat/stream", headers={"X-API-Key": "test-key"}, json={"question": "Hi"}
        )
        assert result.status_code == 502
        assert client.app.state.active_streams == 0


@pytest.mark.asyncio
async def test_upstream_timeout(settings):
    settings.provider = "openai_compatible"

    async def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AppError) as error:
            async for _ in Provider(settings, client).stream(ChatRequest(question="Hi"), []):
                pass
        assert error.value.status == 504


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["data: invalid\n\n", event("partial")])
async def test_protocol_and_incomplete(settings, text):
    settings.provider = "openai_compatible"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=text))
    ) as client:
        with pytest.raises(AppError):
            async for _ in Provider(settings, client).stream(ChatRequest(question="Hi"), []):
                pass


@pytest.mark.asyncio
async def test_client_resource_closed_on_cancel(settings):
    settings.provider = "openai_compatible"

    class Tracked(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield event("first").encode()
            await asyncio.sleep(10)

        async def aclose(self):
            self.closed = True

    tracked = Tracked()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=tracked))
    ) as client:
        stream = Provider(settings, client).stream(ChatRequest(question="Hi"), [])
        assert await anext(stream) == "first"
        await stream.aclose()
        assert tracked.closed is True
