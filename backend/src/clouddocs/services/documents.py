"""Document lifecycle: upload authorization, completion, status refresh, deletion."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from ..config import Settings
from ..errors import Conflict, LimitExceeded, NotFound, UpstreamUnavailable
from ..models import Document, DocumentStatus, IndexState, PresignedPost, UploadUrlRequest
from ..validators import (
    build_s3_key,
    looks_like_pdf,
    validate_document_id,
    validate_upload_request,
    validate_user_id,
)
from .interfaces import DocumentRepository, KnowledgeBase, ObjectStorage

log = logging.getLogger("clouddocs.documents")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return f"doc_{uuid.uuid4().hex}"


class DocumentService:
    def __init__(
        self,
        repo: DocumentRepository,
        storage: ObjectStorage,
        kb: KnowledgeBase,
        settings: Settings,
        now: Callable[[], str] = _now,
        new_id: Callable[[], str] = _new_id,
    ) -> None:
        self._repo, self._storage, self._kb = repo, storage, kb
        self._s, self._now, self._new_id = settings, now, new_id

    def request_upload(self, user_id: str, req: UploadUrlRequest) -> tuple[Document, PresignedPost]:
        validate_user_id(user_id)
        filename = validate_upload_request(req.filename, req.content_type, req.size, self._s)
        if len(self._repo.list(user_id)) >= self._s.max_documents:
            raise LimitExceeded(f"Document limit reached ({self._s.max_documents})")
        doc_id = self._new_id()
        key = build_s3_key(user_id, doc_id)
        ts = self._now()
        doc = Document(
            document_id=doc_id,
            owner_id=user_id,
            filename=filename,
            s3_key=key,
            file_size=req.size,
            content_type="application/pdf",
            status=DocumentStatus.PENDING_UPLOAD,
            created_at=ts,
            updated_at=ts,
        )
        post = self._storage.create_presigned_post(
            key, "application/pdf", self._s.max_file_bytes, self._s.upload_url_ttl_seconds
        )
        self._repo.put(doc)
        return doc, post

    def complete_upload(self, user_id: str, document_id: str) -> Document:
        doc = self._require(user_id, document_id)
        if doc.status != DocumentStatus.PENDING_UPLOAD:
            return doc  # idempotent: repeated calls return the current state
        info = self._storage.head(doc.s3_key)
        if info is None:
            raise Conflict("Upload not found; upload the file first")
        if info.size > self._s.max_file_bytes or not looks_like_pdf(info.first_bytes):
            self._storage.delete(doc.s3_key)
            return self._repo.update_status(
                user_id,
                document_id,
                DocumentStatus.PENDING_UPLOAD,
                DocumentStatus.FAILED,
                "INVALID_FILE",
            )
        doc = self._repo.update_status(
            user_id, document_id, DocumentStatus.PENDING_UPLOAD, DocumentStatus.UPLOADED
        )
        try:
            self._kb.ingest(doc.s3_key, user_id, document_id)
        except Exception:
            log.exception("ingest request failed", extra={"documentId": document_id})
            return self._repo.update_status(
                user_id,
                document_id,
                DocumentStatus.UPLOADED,
                DocumentStatus.FAILED,
                "INGEST_REQUEST_FAILED",
            )
        return self._repo.update_status(
            user_id, document_id, DocumentStatus.UPLOADED, DocumentStatus.INDEXING
        )

    def list_documents(self, user_id: str) -> list[Document]:
        refreshed = (self._refresh(d) for d in self._repo.list(validate_user_id(user_id)))
        return [d for d in refreshed if d is not None]  # None: a delete just finished

    def get_document(self, user_id: str, document_id: str) -> Document:
        doc = self._refresh(self._require(user_id, document_id))
        if doc is None:
            raise NotFound("Document not found")
        return doc

    def delete_document(self, user_id: str, document_id: str) -> Document | None:
        """Return None once fully removed; return the DELETING doc while the index still has it."""
        doc = self._require(user_id, document_id)
        if doc.status != DocumentStatus.DELETING:
            doc = self._repo.update_status(
                user_id, document_id, doc.status, DocumentStatus.DELETING
            )
        try:
            self._kb.delete(doc.s3_key)
        except Exception:
            # e.g. a document that never reached the index: the status check below decides.
            log.warning(
                "kb delete request failed", extra={"documentId": document_id}, exc_info=True
            )
        try:
            gone = self._kb.index_state(doc.s3_key) == IndexState.NOT_FOUND
        except Exception as exc:
            log.exception("index status check failed", extra={"documentId": document_id})
            raise UpstreamUnavailable("Could not remove indexed content; retry later") from exc
        if not gone:
            return doc  # stays DELETING; a later list/get finishes it once the index confirms
        self._finish_delete(doc)
        return None

    def _finish_delete(self, doc: Document) -> None:
        """Only after the index no longer has it: remove the source file, then the record."""
        self._storage.delete(doc.s3_key)
        self._repo.delete(doc.owner_id, doc.document_id)

    # -- helpers ---------------------------------------------------------
    def _require(self, user_id: str, document_id: str) -> Document:
        validate_user_id(user_id)
        validate_document_id(document_id)
        doc = self._repo.get(user_id, document_id)  # lookup is scoped by owner (PK)
        if doc is None:
            raise NotFound("Document not found")
        return doc

    def _refresh(self, doc: Document) -> Document | None:
        if doc.status == DocumentStatus.DELETING:
            try:
                gone = self._kb.index_state(doc.s3_key) == IndexState.NOT_FOUND
            except Exception:
                log.exception("index status check failed", extra={"documentId": doc.document_id})
                return doc
            if gone:
                self._finish_delete(doc)
                return None
            return doc
        if doc.status != DocumentStatus.INDEXING:
            return doc
        try:
            state = self._kb.index_state(doc.s3_key)
        except Exception:
            log.exception("index status check failed", extra={"documentId": doc.document_id})
            return doc  # keep INDEXING; transient errors must not flip state
        if state == IndexState.INDEXED:
            return self._repo.update_status(
                doc.owner_id, doc.document_id, DocumentStatus.INDEXING, DocumentStatus.READY
            )
        if state in (IndexState.FAILED, IndexState.NOT_FOUND):
            return self._repo.update_status(
                doc.owner_id,
                doc.document_id,
                DocumentStatus.INDEXING,
                DocumentStatus.FAILED,
                "INDEXING_FAILED",
            )
        return doc
