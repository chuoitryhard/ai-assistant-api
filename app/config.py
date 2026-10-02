import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator


class Settings(BaseModel):
    provider: Literal["demo", "openai_compatible"] = "demo"
    api_keys: tuple[str, ...] = ("dev-student-key",)
    data_dir: Path = Path("data")
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: SecretStr = SecretStr("local")
    llm_model: str = "qwen2.5:3b"
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    max_units: int = Field(default=80, ge=1, le=500)
    max_text_chars: int = Field(default=200_000, ge=1000)
    max_documents: int = Field(default=200, ge=1)
    max_active_streams: int = Field(default=8, ge=1)
    llm_timeout: float = Field(default=45, gt=0)
    demo_delay: float = Field(default=0.025, ge=0)
    max_stream_chars: int = Field(default=60_000, ge=100)

    @model_validator(mode="after")
    def validate_configuration(self):
        from urllib.parse import urlparse

        url = urlparse(self.llm_base_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.query or url.fragment:
            raise ValueError("LLM_BASE_URL must be an HTTP(S) base URL without query/fragment")
        if not self.api_keys or any(not key.strip() for key in self.api_keys):
            raise ValueError("API_KEYS must contain at least one non-empty key")
        return self

    @classmethod
    def from_env(cls):
        values = {}
        for name in cls.model_fields:
            value = os.getenv(name.upper())
            if value is not None:
                values[name] = tuple(value.split(",")) if name == "api_keys" else value
        return cls(**values)
