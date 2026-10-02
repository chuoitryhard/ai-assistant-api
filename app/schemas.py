from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(StrictSchema):
    question: str = Field(min_length=1, max_length=4000, description="Câu hỏi hoặc yêu cầu tóm tắt")
    document_ids: list[UUID] = Field(default_factory=list, max_length=5)
    task: Literal["answer", "summarize"] = "answer"
    temperature: float = Field(default=0.2, ge=0, le=1, strict=True)
    max_tokens: int = Field(default=512, ge=16, le=2048, strict=True)


class DocumentOut(BaseModel):
    id: UUID
    name: str
    kind: Literal["pdf", "pptx", "txt"]
    status: Literal["queued", "processing", "ready", "failed"]
    created_at: str
    units: int = 0
    char_count: int = 0
    error: str | None = None


class DocumentList(BaseModel):
    items: list[DocumentOut]


class Source(BaseModel):
    document_id: UUID
    name: str
    unit: int
    excerpt: str


class ChatOut(BaseModel):
    answer: str
    provider: str
    sources: list[Source]


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: list[dict] = Field(default_factory=list)


class ErrorOut(BaseModel):
    error: ErrorBody


class StreamMeta(BaseModel):
    provider: str
    sources: list[Source]


class StreamToken(BaseModel):
    text: str


class StreamDone(BaseModel):
    characters: int


class HealthOut(BaseModel):
    status: Literal["ok"]
    provider: str
    worker_running: bool
