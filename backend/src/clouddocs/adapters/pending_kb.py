"""Placeholder KnowledgeBase used until the Bedrock Knowledge Base exists (Phase 3).

It never claims a document is indexed: uploaded documents stay INDEXING, and
questions get the standard "no evidence" answer. This keeps the "READY only
after the index confirms" rule true even before RAG is wired.
"""

from __future__ import annotations

import logging

from ..models import IndexState, RagResult

log = logging.getLogger("clouddocs.kb")


class PendingKnowledgeBase:
    def ingest(self, s3_key: str, owner_id: str, document_id: str) -> None:
        log.info(
            "knowledge base not configured yet; ingestion deferred",
            extra={"documentId": document_id},
        )

    def index_state(self, s3_key: str) -> IndexState:
        return IndexState.IN_PROGRESS

    def delete(self, s3_key: str) -> None:
        return None

    def query(self, question: str, owner_id: str) -> RagResult:
        return RagResult(answer="", references=[])
