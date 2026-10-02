import asyncio
import logging
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfReader

from app.config import Settings
from app.store import Store

logger = logging.getLogger(__name__)


def extract(path: str, kind: str, max_units: int, max_chars: int) -> list[dict]:
    """Blocking parsers run in a dedicated process, never on the event loop."""
    chunks = []
    total = 0

    def add(unit, text):
        nonlocal total
        text = text.replace("\x00", "").strip()
        total += len(text)
        if total > max_chars:
            raise ValueError("Nội dung vượt giới hạn ký tự trích xuất")
        chunks.append({"unit": unit, "text": text})

    if kind == "pdf":
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("PDF có mật khẩu không được hỗ trợ")
        if len(reader.pages) > max_units:
            raise ValueError("PDF vượt giới hạn số trang")
        for i, page in enumerate(reader.pages, 1):
            # Avoid pathological content streams in this educational deployment.
            content = page.get_contents()
            if content and len(content.get_data()) > 8 * 1024 * 1024:
                raise ValueError("Trang PDF quá phức tạp")
            add(i, page.extract_text() or "")
    elif kind == "pptx":
        # Parse slide XML directly, avoid loading images and embedded media.
        import re
        from defusedxml.ElementTree import fromstring

        with ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 5000 or sum(i.file_size for i in infos) > 100 * 1024 * 1024:
                raise ValueError("PPTX có dung lượng giải nén quá lớn")
            slides = sorted(
                (i for i in infos if re.fullmatch(r"ppt/slides/slide\d+\.xml", i.filename)),
                key=lambda x: int(re.search(r"slide(\d+)", x.filename)[1]),
            )
            if len(slides) > max_units:
                raise ValueError("PPTX vượt giới hạn số slide")
            for index, info in enumerate(slides, 1):
                if info.file_size > 2 * 1024 * 1024:
                    raise ValueError("XML slide quá lớn")
                root = fromstring(archive.read(info))
                texts = root.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}t")
                add(index, "\n".join(node.text or "" for node in texts))
    else:
        add(1, Path(path).read_text(encoding="utf-8"))
    if not any(c["text"] for c in chunks):
        raise ValueError("Không có văn bản. PDF scan cần OCR ngoài phạm vi phiên bản này")
    return chunks


async def worker(store: Store, settings: Settings, pool, wake: asyncio.Event):
    while True:
        row = await store.claim()
        if row is None:
            wake.clear()
            try:
                await asyncio.wait_for(wake.wait(), timeout=0.5)
            except TimeoutError:
                pass
            continue
        logger.info("extraction_started id=%s", row["id"])
        try:
            chunks = await asyncio.get_running_loop().run_in_executor(
                pool, extract, row["path"], row["kind"], settings.max_units, settings.max_text_chars
            )
            await store.finish(row["id"], chunks)
            logger.info("extraction_ready id=%s units=%s", row["id"], len(chunks))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("extraction_failed id=%s type=%s", row["id"], type(exc).__name__)
            message = str(exc) if isinstance(exc, ValueError) else "Tài liệu hỏng hoặc không đọc được"
            await store.fail(row["id"], message)
