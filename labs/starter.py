"""Hands-on lab starter. TODOs are intentional and are not production code."""

import json
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(title="FastAPI hands-on lab")


class Prompt(BaseModel):
    question: str = Field(min_length=1, max_length=120)
    # Exercise 1: forbid extra fields and strip whitespace.


def config():
    return {"delay": 0.02}


@app.post("/stream")
async def stream(prompt: Prompt, settings: Annotated[dict, Depends(config)]):
    async def events():
        for word in prompt.question.split():
            # Exercise 2: await an async timer and produce token SSE events.
            yield json.dumps({"text": word})
        # Exercise 3: emit a done event and test dependency overrides.

    return StreamingResponse(events(), media_type="text/event-stream")
