"""Actual TCP streaming check. Run while the gateway serves on localhost:8000."""

import asyncio
import json
import os
import time
from pathlib import Path

import httpx


async def main():
    base = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    key = os.getenv("API_KEY", "dev-student-key")
    headers = {"X-API-Key": key}
    start = time.perf_counter()
    token_times = []
    events = []
    async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
        async with client.stream(
            "POST",
            base + "/api/v1/chat/stream",
            headers=headers,
            json={"question": "Giải thích async và await trong FastAPI"},
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                    events.append(event)
                    if event == "token":
                        token_times.append((time.perf_counter() - start) * 1000)
        assert events[-1] == "done" and len(token_times) > 2
        assert token_times[-1] - token_times[0] > 50, "Tokens were buffered"
        response = await client.post(
            base + "/api/v1/documents",
            headers=headers,
            files={"file": ("smoke.txt", b"FastAPI uses Pydantic models and dependency injection.")},
        )
        response.raise_for_status()
        doc_id = response.json()["id"]
        for _ in range(200):
            state = (await client.get(base + f"/api/v1/documents/{doc_id}", headers=headers)).json()
            if state["status"] in {"ready", "failed"}:
                break
            await asyncio.sleep(0.03)
        assert state["status"] == "ready", state
        result = await client.post(
            base + "/api/v1/chat",
            headers=headers,
            json={"question": "What is Pydantic?", "document_ids": [doc_id]},
        )
        assert result.json()["sources"][0]["document_id"] == doc_id
        assert (await client.delete(base + f"/api/v1/documents/{doc_id}", headers=headers)).status_code == 204
    evidence = {
        "provider": "demo",
        "first_token_ms": round(token_times[0], 2),
        "last_token_ms": round(token_times[-1], 2),
        "token_events": len(token_times),
        "token_times_ms": token_times,
        "document_flow": "upload -> ready -> context -> delete PASS",
        "note": "Actual localhost TCP. Demo delay, not real-model latency.",
    }
    Path("docs/evidence/http-smoke.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(evidence)


if __name__ == "__main__":
    asyncio.run(main())
