"""SQLite work is synchronous and explicitly sent to a thread via asyncio.to_thread."""

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

from app.errors import AppError


class Store:
    def __init__(self, path: Path):
        self.path = path

    def _execute(self, sql, args=(), *, all_rows=False):
        with sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            cursor = db.execute(sql, args)
            if all_rows:
                return [dict(row) for row in cursor.fetchall()]
            row = cursor.fetchone()
            return dict(row) if row else None

    async def execute(self, *args, **kwargs):
        return await asyncio.to_thread(self._execute, *args, **kwargs)

    async def init(self):
        await self.execute("PRAGMA journal_mode=WAL")
        await self.execute("""CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
            kind TEXT NOT NULL, path TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, units INTEGER NOT NULL DEFAULT 0,
            char_count INTEGER NOT NULL DEFAULT 0, chunks TEXT NOT NULL DEFAULT '[]',
            error TEXT)""")
        # Single-process worker: interrupted tasks can safely be extracted again.
        await self.execute("UPDATE documents SET status='queued' WHERE status='processing'")

    async def create(self, doc_id, owner, name, kind, path, limit):
        def insert():
            with sqlite3.connect(self.path, timeout=10) as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute("SELECT count(*) FROM documents").fetchone()[0]
                if count >= limit:
                    raise AppError(429, "document_limit", "Đã đạt giới hạn lưu tài liệu")
                db.execute(
                    "INSERT INTO documents(id,owner,name,kind,path,status,created_at) VALUES(?,?,?,?,?,'queued',?)",
                    (doc_id, owner, name, kind, str(path), datetime.now(UTC).isoformat()),
                )

        await asyncio.to_thread(insert)

    async def get(self, doc_id, owner):
        row = await self.execute("SELECT * FROM documents WHERE id=? AND owner=?", (str(doc_id), owner))
        if not row:
            raise AppError(404, "document_not_found", "Không tìm thấy tài liệu")
        return row

    async def list(self, owner):
        return await self.execute(
            "SELECT * FROM documents WHERE owner=? ORDER BY created_at DESC", (owner,), all_rows=True
        )

    async def claim(self):
        def transaction():
            with sqlite3.connect(self.path, timeout=10) as db:
                db.row_factory = sqlite3.Row
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT * FROM documents WHERE status='queued' ORDER BY created_at LIMIT 1"
                ).fetchone()
                if row:
                    db.execute("UPDATE documents SET status='processing' WHERE id=?", (row["id"],))
                return dict(row) if row else None

        return await asyncio.to_thread(transaction)

    async def finish(self, doc_id, chunks):
        await self.execute(
            "UPDATE documents SET status='ready', chunks=?, units=?, char_count=?, error=NULL WHERE id=?",
            (
                json.dumps(chunks, ensure_ascii=False),
                len(chunks),
                sum(len(c["text"]) for c in chunks),
                doc_id,
            ),
        )

    async def fail(self, doc_id, message):
        await self.execute("UPDATE documents SET status='failed', error=? WHERE id=?", (message, doc_id))

    async def retry(self, doc_id, owner):
        row = await self.get(doc_id, owner)
        if row["status"] != "failed":
            raise AppError(409, "invalid_state", "Chỉ chạy lại tài liệu bị lỗi")
        await self.execute("UPDATE documents SET status='queued', error=NULL WHERE id=?", (str(doc_id),))
        return await self.get(doc_id, owner)

    async def delete(self, doc_id, owner):
        def transaction():
            with sqlite3.connect(self.path, timeout=10) as db:
                db.row_factory = sqlite3.Row
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT * FROM documents WHERE id=? AND owner=?", (str(doc_id), owner)
                ).fetchone()
                if not row:
                    raise AppError(404, "document_not_found", "Không tìm thấy tài liệu")
                if row["status"] in {"queued", "processing"}:
                    raise AppError(409, "document_busy", "Chờ tài liệu xử lý xong trước khi xóa")
                db.execute("DELETE FROM documents WHERE id=?", (str(doc_id),))
                return row["path"]

        path = await asyncio.to_thread(transaction)
        await asyncio.to_thread(Path(path).unlink, missing_ok=True)
