import asyncio
import json
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="FastAPI lab solution")


class Prompt(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=120)


def config():
    return {"delay": 0.02}


@app.post("/stream")
async def stream(prompt: Prompt, settings: Annotated[dict, Depends(config)]):
    async def events():
        for word in prompt.question.split():
            await asyncio.sleep(settings["delay"])
            yield f"event: token\ndata: {json.dumps({'text': word}, ensure_ascii=False)}\n\n"
        yield 'event: done\ndata: {"ok": true}\n\n'

    return StreamingResponse(events(), media_type="text/event-stream")
