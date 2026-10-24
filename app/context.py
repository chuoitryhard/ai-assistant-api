import json
import re

from app.errors import AppError
from app.schemas import ChatRequest, Source
from app.store import Store


async def build_context(payload: ChatRequest, store: Store, owner: str):
    candidates = []
    terms = set(re.findall(r"\w+", payload.question.casefold()))
    for doc_id in dict.fromkeys(payload.document_ids):
        row = await store.get(doc_id, owner)
        if row["status"] != "ready":
            raise AppError(409, "document_not_ready", "Tài liệu chưa xử lý thành công")
        for chunk in json.loads(row["chunks"]):
            # Fixed windows prevent a long page from swallowing the context budget.
            text = chunk["text"]
            for start in range(0, len(text), 1200):
                excerpt = text[start : start + 1400]
                score = len(terms.intersection(re.findall(r"\w+", excerpt.casefold())))
                candidates.append(
                    (score, Source(document_id=doc_id, name=row["name"], unit=chunk["unit"], excerpt=excerpt))
                )
    if payload.task == "answer":
        candidates.sort(key=lambda pair: pair[0], reverse=True)
    # A lexical selection strategy, not vector RAG and not a whole-book summary.
    sources = [source for _, source in candidates[:6]]
    if payload.task == "summarize" and not sources:
        raise AppError(422, "document_required", "Tóm tắt cần ít nhất một tài liệu có văn bản")
    return sources
