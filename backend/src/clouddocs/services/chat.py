"""RAG question answering with citations resolved against owned documents."""

from __future__ import annotations

import re

from ..config import Settings
from ..lang import NO_EVIDENCE, no_evidence_message
from ..models import ChatRequest, Citation, RagResult
from ..validators import document_id_from_key, validate_question, validate_user_id
from .interfaces import DocumentRepository, KnowledgeBase

# Kept for callers and tests; the actual reply follows the question's language (UI-06).
NO_EVIDENCE_MESSAGE = NO_EVIDENCE["en"]
MAX_EXCERPT_CHARS = 500


def trim_excerpt(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    """Collapse whitespace and cut at a word boundary, marking the cut with an ellipsis."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(" ", 1)[0] if " " in flat[:limit] else flat[:limit]
    return cut.rstrip(" ,;:.") + "…"
MAX_CITATIONS = 5
_S3_URI_RE = re.compile(r"^s3://[^/]+/(.+)$")


def s3_uri_to_key(uri: str) -> str | None:
    m = _S3_URI_RE.match(uri)
    return m.group(1) if m else None


class ChatService:
    def __init__(self, repo: DocumentRepository, kb: KnowledgeBase, settings: Settings) -> None:
        self._repo, self._kb, self._s = repo, kb, settings

    def query(self, user_id: str, req: ChatRequest) -> tuple[str, list[Citation]]:
        validate_user_id(user_id)
        question = validate_question(req.question, self._s)
        result = self._kb.query(question, user_id)  # retrieval filtered to this user
        citations = self._resolve_citations(user_id, result)
        if not citations:
            # No verifiable evidence: never return a model answer dressed up with sources.
            return no_evidence_message(question), []
        return result.answer, citations

    def _resolve_citations(self, user_id: str, result: RagResult) -> list[Citation]:
        out: list[Citation] = []
        seen: set[tuple[str, str]] = set()
        for ref in result.references:
            key = s3_uri_to_key(ref.s3_uri)
            doc_id = document_id_from_key(key) if key else None
            if doc_id is None:
                continue
            doc = self._repo.get(user_id, doc_id)  # defence in depth: must be owned and known
            if doc is None:
                continue
            excerpt = trim_excerpt(ref.text)
            if not excerpt or (doc_id, excerpt) in seen:
                continue
            seen.add((doc_id, excerpt))
            out.append(Citation(document_id=doc_id, document_name=doc.filename, excerpt=excerpt))
            if len(out) >= MAX_CITATIONS:
                break
        return out
