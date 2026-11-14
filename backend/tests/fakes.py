"""In-memory fakes for the AWS ports. No network, no credentials."""

from __future__ import annotations

from clouddocs.errors import Conflict
from clouddocs.models import (
    Document,
    DocumentStatus,
    IndexState,
    PresignedPost,
    RagResult,
)
from clouddocs.services.interfaces import ObjectInfo


class FakeRepo:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], Document] = {}

    def put(self, doc: Document) -> None:
        self.items[(doc.owner_id, doc.document_id)] = doc

    def get(self, owner_id: str, document_id: str) -> Document | None:
        return self.items.get((owner_id, document_id))

    def list(self, owner_id: str) -> list[Document]:
        return [d for (o, _), d in self.items.items() if o == owner_id]

    def update_status(
        self,
        owner_id: str,
        document_id: str,
        expected: DocumentStatus,
        new: DocumentStatus,
        error_code: str | None = None,
    ) -> Document:
        from clouddocs.status import ensure_transition

        doc = self.items[(owner_id, document_id)]
        if doc.status != expected:
            raise Conflict("Document status changed concurrently")
        ensure_transition(expected, new)
        updated = doc.model_copy(update={"status": new, "error_code": error_code})
        self.items[(owner_id, document_id)] = updated
        return updated

    def delete(self, owner_id: str, document_id: str) -> None:
        self.items.pop((owner_id, document_id), None)


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_head = False

    def create_presigned_post(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> PresignedPost:
        return PresignedPost(
            url="https://fake-bucket.s3.amazonaws.com/",
            fields={"key": key, "Content-Type": content_type},
        )

    def head(self, key: str) -> ObjectInfo | None:
        data = self.objects.get(key)
        return None if data is None else ObjectInfo(size=len(data), first_bytes=data[:8])

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class FakeKB:
    def __init__(self) -> None:
        self.states: dict[str, IndexState] = {}
        self.ingest_error: Exception | None = None
        self.delete_completes = True
        self.result = RagResult(answer="", references=[])
        self.queries: list[str] = []

    def ingest(self, s3_key: str, owner_id: str, document_id: str) -> None:
        if self.ingest_error:
            raise self.ingest_error
        self.states[s3_key] = IndexState.IN_PROGRESS

    def index_state(self, s3_key: str) -> IndexState:
        return self.states.get(s3_key, IndexState.NOT_FOUND)

    def delete(self, s3_key: str) -> None:
        if self.delete_completes:
            self.states.pop(s3_key, None)

    def query(self, question: str) -> RagResult:
        self.queries.append(question)
        return self.result
