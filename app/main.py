import asyncio
import contextlib
import json
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.config import Settings
from app.context import build_context
from app.dependencies import Configuration, Database, Owner, get_provider
from app.errors import AppError
from app.extraction import worker
from app.provider import Provider
from app.schemas import (
    ChatOut,
    ChatRequest,
    DocumentList,
    DocumentOut,
    ErrorOut,
    HealthOut,
    StreamDone,
    StreamMeta,
    StreamToken,
)
from app.store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("gateway")
STATIC = Path(__file__).parent / "static"
ERROR_RESPONSES = {s: {"model": ErrorOut} for s in (401, 404, 409, 413, 415, 422, 429, 502, 504)}


class RequestLogMiddleware:
    """Pure ASGI middleware preserves streaming, logs after the last body chunk."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status = 500

        async def send_with_metadata(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message["headers"]) + [(b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_metadata)
        finally:
            logger.info(
                "request id=%s method=%s path=%s status=%s duration_ms=%.2f",
                request_id,
                scope["method"],
                scope["path"],
                status,
                (time.perf_counter() - start) * 1000,
            )


def error_response(request, status, code, message, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", "unknown"),
                "details": details or [],
            }
        },
    )


def encode_event(event: str, data: BaseModel | dict) -> str:
    content = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
    return f"event: {event}\ndata: {json.dumps(content, ensure_ascii=False)}\n\n"


def create_app(settings: Settings | None = None, *, transport=None) -> FastAPI:
    settings = settings or Settings.from_env()

    @contextlib.asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        (settings.data_dir / "uploads").mkdir(exist_ok=True)
        store = Store(settings.data_dir / "gateway.sqlite3")
        await store.init()
        pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout, connect=10),
            limits=httpx.Limits(max_connections=settings.max_active_streams, max_keepalive_connections=8),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            app.state.settings, app.state.store = settings, store
            app.state.provider = Provider(settings, client)
            app.state.active_streams = 0
            app.state.wake = asyncio.Event()
            task = asyncio.create_task(worker(store, settings, pool, app.state.wake))
            app.state.worker = task
            try:
                yield
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                # Graceful shutdown waits for any parser already running.
                await asyncio.to_thread(pool.shutdown, wait=True, cancel_futures=True)

    app = FastAPI(
        title="StudyGateway AI Assistant API",
        version="1.0.0",
        lifespan=lifespan,
        description="Trợ lý học tập với SSE và trích xuất PDF/PPTX qua worker. Demo không gọi LLM.",
    )
    app.add_middleware(RequestLogMiddleware)

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo uploaded content, questions, or API keys into errors/logs.
        details = [{"loc": list(e["loc"]), "type": e["type"], "message": e["msg"]} for e in exc.errors()]
        return error_response(request, 422, "validation_error", "Dữ liệu không đúng schema", details)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, exc.status_code, "http_error", str(exc.detail))

    @app.get("/health", response_model=HealthOut, tags=["System"])
    async def health(request: Request):
        return {
            "status": "ok",
            "provider": settings.provider,
            "worker_running": not request.app.state.worker.done(),
        }

    @app.get("/", include_in_schema=False)
    def home():
        # FileResponse reads the file off the event loop.
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.post(
        "/api/v1/documents",
        response_model=DocumentOut,
        status_code=202,
        responses=ERROR_RESPONSES,
        tags=["Documents"],
    )
    async def upload_document(
        request: Request,
        owner: Owner,
        store: Database,
        config: Configuration,
        file: Annotated[UploadFile, File(description="PDF có text, PPTX hoặc TXT UTF-8, tối đa 20 MiB")],
    ):
        name = (file.filename or "document").replace("\\", "/").split("/")[-1][:180]
        kind = Path(name).suffix.lower().lstrip(".")
        if kind not in {"pdf", "pptx", "txt"}:
            await file.close()
            raise AppError(415, "unsupported_file", "Chỉ nhận PDF, PPTX hoặc TXT")
        doc_id = str(uuid4())
        path = config.data_dir / "uploads" / f"{doc_id}.{kind}"
        count, signature = 0, b""
        try:
            # Each file read/write yields to threadpool I/O, bounded memory per chunk.
            handle = await asyncio.to_thread(path.open, "wb")
            try:
                while data := await file.read(64 * 1024):
                    count += len(data)
                    if count > config.max_upload_bytes:
                        raise AppError(413, "file_too_large", "Tài liệu vượt giới hạn dung lượng")
                    if not signature:
                        signature = data[:8]
                    await asyncio.to_thread(handle.write, data)
            finally:
                await asyncio.to_thread(handle.close)
            if not count:
                raise AppError(422, "empty_file", "Tệp rỗng")
            if kind == "pdf" and not signature.startswith(b"%PDF-"):
                raise AppError(415, "invalid_signature", "Tệp không có chữ ký PDF")
            if kind == "pptx" and not signature.startswith(b"PK"):
                raise AppError(415, "invalid_signature", "Tệp không có chữ ký PPTX ZIP")
            await store.create(doc_id, owner, name, kind, path, config.max_documents)
        except BaseException:
            await asyncio.to_thread(path.unlink, missing_ok=True)
            raise
        finally:
            await file.close()
        request.app.state.wake.set()
        return await store.get(doc_id, owner)

    @app.get("/api/v1/documents", response_model=DocumentList, responses=ERROR_RESPONSES, tags=["Documents"])
    async def list_documents(owner: Owner, store: Database):
        return {"items": await store.list(owner)}

    @app.get(
        "/api/v1/documents/{document_id}",
        response_model=DocumentOut,
        responses=ERROR_RESPONSES,
        tags=["Documents"],
    )
    async def get_document(document_id: UUID, owner: Owner, store: Database):
        return await store.get(document_id, owner)

    @app.post(
        "/api/v1/documents/{document_id}/retry",
        response_model=DocumentOut,
        status_code=202,
        responses=ERROR_RESPONSES,
        tags=["Documents"],
    )
    async def retry_document(document_id: UUID, request: Request, owner: Owner, store: Database):
        result = await store.retry(document_id, owner)
        request.app.state.wake.set()
        return result

    @app.delete(
        "/api/v1/documents/{document_id}", status_code=204, responses=ERROR_RESPONSES, tags=["Documents"]
    )
    async def delete_document(document_id: UUID, owner: Owner, store: Database):
        await store.delete(document_id, owner)
        return Response(status_code=204)

    async def prepare(payload, owner, store, provider, request):
        sources = await build_context(payload, store, owner)
        # No await between the check and increment: atomic on this one event loop.
        if request.app.state.active_streams >= settings.max_active_streams:
            raise AppError(429, "stream_limit", "Đã đạt giới hạn yêu cầu AI đồng thời")
        request.app.state.active_streams += 1
        stream = provider.stream(payload, sources)
        try:
            first = await anext(stream, "")
            if len(first) > settings.max_stream_chars:
                raise AppError(502, "output_limit", "LLM trả về quá nhiều nội dung")
        except BaseException:
            await stream.aclose()
            request.app.state.active_streams -= 1
            raise
        return sources, stream, first

    @app.post("/api/v1/chat", response_model=ChatOut, responses=ERROR_RESPONSES, tags=["Assistant"])
    async def chat(
        payload: ChatRequest, request: Request, owner: Owner, store: Database, provider=Depends(get_provider)
    ):
        sources, stream, first = await prepare(payload, owner, store, provider, request)
        try:
            answer = first
            async for token in stream:
                answer += token
                if len(answer) > settings.max_stream_chars:
                    raise AppError(502, "output_limit", "LLM trả về quá nhiều nội dung")
            return ChatOut(answer=answer, provider=settings.provider, sources=sources)
        finally:
            await stream.aclose()
            request.app.state.active_streams -= 1

    @app.post(
        "/api/v1/chat/stream",
        response_class=StreamingResponse,
        responses={
            **ERROR_RESPONSES,
            200: {
                "content": {"text/event-stream": {}},
                "description": "SSE: meta, token, done; error nếu lỗi xảy ra sau HTTP 200",
            },
        },
        tags=["Assistant"],
    )
    async def chat_stream(
        payload: ChatRequest, request: Request, owner: Owner, store: Database, provider=Depends(get_provider)
    ):
        sources, stream, first = await prepare(payload, owner, store, provider, request)

        async def events():
            characters = 0
            try:
                yield encode_event("meta", StreamMeta(provider=settings.provider, sources=sources))
                if first:
                    characters += len(first)
                    yield encode_event("token", StreamToken(text=first))
                async for token in stream:
                    if await request.is_disconnected():
                        break
                    characters += len(token)
                    if characters > settings.max_stream_chars:
                        raise AppError(502, "output_limit", "LLM trả về quá nhiều nội dung")
                    yield encode_event("token", StreamToken(text=token))
                else:
                    yield encode_event("done", StreamDone(characters=characters))
            except AppError as exc:
                yield encode_event("error", {"code": exc.code, "message": exc.message})
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("stream_failed request_id=%s", request.state.request_id)
                yield encode_event(
                    "error", {"code": "stream_error", "message": "Luồng phản hồi bị gián đoạn"}
                )
            finally:
                await stream.aclose()
                request.app.state.active_streams -= 1

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
