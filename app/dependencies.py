import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from app.config import Settings
from app.errors import AppError
from app.store import Store

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_provider(request: Request):
    return request.app.state.provider


def require_owner(
    settings: Annotated[Settings, Depends(get_settings)],
    key: Annotated[str | None, Security(api_key_header)],
) -> str:
    if key is None or not any(secrets.compare_digest(key, allowed) for allowed in settings.api_keys):
        raise AppError(401, "unauthorized", "X-API-Key không hợp lệ")
    return hashlib.sha256(key.encode()).hexdigest()


Owner = Annotated[str, Depends(require_owner)]
Database = Annotated[Store, Depends(get_store)]
Configuration = Annotated[Settings, Depends(get_settings)]
