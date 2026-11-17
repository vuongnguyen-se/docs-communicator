"""Typed request/response and domain models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocumentStatus(StrEnum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADED = "UPLOADED"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"
    DELETING = "DELETING"


class IndexState(StrEnum):
    """Provider-neutral state of a document inside the knowledge base."""

    IN_PROGRESS = "IN_PROGRESS"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    NOT_FOUND = "NOT_FOUND"


class Document(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    owner_id: str
    filename: str
    s3_key: str
    file_size: int
    content_type: str
    status: DocumentStatus
    created_at: str
    updated_at: str
    ingestion_job_id: str | None = None
    error_code: str | None = None

    def public(self) -> dict[str, object]:
        """Client-safe view: never exposes ownerId or the S3 key."""
        return {
            "documentId": self.document_id,
            "filename": self.filename,
            "fileSize": self.file_size,
            "status": self.status.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "errorCode": self.error_code,
        }


class UploadUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    content_type: str = Field(alias="contentType")
    size: int = Field(gt=0)


class PresignedPost(BaseModel):
    url: str
    fields: dict[str, str]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)


class Citation(BaseModel):
    document_id: str = Field(serialization_alias="documentId")
    document_name: str = Field(serialization_alias="documentName")
    excerpt: str


class RetrievedReference(BaseModel):
    """One passage returned by the knowledge base, before ownership resolution."""

    s3_uri: str
    text: str


class RagResult(BaseModel):
    answer: str
    references: list[RetrievedReference]
