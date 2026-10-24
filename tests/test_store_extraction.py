import json
from zipfile import ZipFile

import pytest

from app.extraction import extract
from app.store import Store


@pytest.mark.asyncio
async def test_restart_recovers_processing(tmp_path):
    store = Store(tmp_path / "test.sqlite")
    await store.init()
    await store.create("id", "owner", "test.txt", "txt", tmp_path / "test.txt", 10)
    assert (await store.claim())["id"] == "id"
    assert (await store.get("id", "owner"))["status"] == "processing"
    await Store(tmp_path / "test.sqlite").init()
    assert (await store.get("id", "owner"))["status"] == "queued"


@pytest.mark.asyncio
async def test_store_roundtrip(tmp_path):
    store = Store(tmp_path / "test.sqlite")
    await store.init()
    await store.create("id", "owner", "test.txt", "txt", tmp_path / "test.txt", 10)
    await store.finish("id", [{"unit": 1, "text": "Xin chào"}])
    result = await store.get("id", "owner")
    assert json.loads(result["chunks"])[0]["text"] == "Xin chào"
    assert result["char_count"] == 8


def test_pptx_extract(tmp_path):
    path = tmp_path / "lesson.pptx"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>FastAPI lesson</a:t></p>',
        )
    assert extract(str(path), "pptx", 80, 2000) == [{"unit": 1, "text": "FastAPI lesson"}]


def test_extraction_text_limit(tmp_path):
    path = tmp_path / "lesson.txt"
    path.write_text("x" * 1001)
    with pytest.raises(ValueError):
        extract(str(path), "txt", 80, 1000)


def test_encrypted_pdf(tmp_path):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    path = tmp_path / "locked.pdf"
    writer.write(path)
    with pytest.raises(ValueError, match="mật khẩu"):
        extract(str(path), "pdf", 80, 1000)
