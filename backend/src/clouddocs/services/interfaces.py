"""Ports to AWS. Real adapters (boto3) arrive in Phase 2; tests use in-memory fakes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import Document, DocumentStatus, IndexState, PresignedPost, RagResult


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    first_bytes: bytes


class DocumentRepository(Protocol):
    def put(self, doc: Document) -> None: ...

    def get(self, owner_id: str, document_id: str) -> Document | None: ...

    def list(self, owner_id: str) -> list[Document]: ...

    def update_status(
        self,
        owner_id: str,
        document_id: str,
        expected: DocumentStatus,
        new: DocumentStatus,
        error_code: str | None = None,
    ) -> Document:
        """Conditional update (compare-and-set). Raises Conflict if status != expected."""
        ...

    def delete(self, owner_id: str, document_id: str) -> None: ...


class ObjectStorage(Protocol):
    def create_presigned_post(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> PresignedPost: ...

    def head(self, key: str) -> ObjectInfo | None: ...

    def delete(self, key: str) -> None: ...


class KnowledgeBase(Protocol):
    def ingest(self, s3_key: str, owner_id: str, document_id: str) -> None: ...

    def index_state(self, s3_key: str) -> IndexState: ...

    def delete(self, s3_key: str) -> None: ...

    def query(self, question: str) -> RagResult: ...
