"""Input validation. Never trust client-declared metadata."""

from __future__ import annotations

import re
import unicodedata

from .config import Settings
from .errors import ValidationFailed

PDF_CONTENT_TYPE = "application/pdf"
PDF_MAGIC = b"%PDF-"
_DOC_ID_RE = re.compile(r"^doc_[0-9a-f]{32}$")
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_KEY_RE = re.compile(r"^uploads/([A-Za-z0-9_-]{1,128})/(doc_[0-9a-f]{32})\.pdf$")


def validate_upload_request(filename: str, content_type: str, size: int, s: Settings) -> str:
    """Return a cleaned display filename or raise ValidationFailed."""
    if content_type.lower() != PDF_CONTENT_TYPE:
        raise ValidationFailed("Only PDF files are supported")
    if size <= 0 or size > s.max_file_bytes:
        raise ValidationFailed(f"File size must be between 1 byte and {s.max_file_bytes} bytes")
    return clean_filename(filename, s.max_filename_chars)


def clean_filename(filename: str, max_chars: int) -> str:
    # Keep only the final path component and drop control characters.
    # Vietnamese (and other Unicode) letters are preserved.
    name = filename.replace("\\", "/").split("/")[-1]
    normalized = unicodedata.normalize("NFC", name)
    name = "".join(c for c in normalized if unicodedata.category(c)[0] != "C").strip()
    if not name or name.lower() == ".pdf" or not name.lower().endswith(".pdf"):
        raise ValidationFailed("Filename must end with .pdf")
    if len(name) > max_chars:
        raise ValidationFailed("Filename is too long")
    return name


def validate_question(question: str, s: Settings) -> str:
    q = question.strip()
    if not q:
        raise ValidationFailed("Question must not be empty")
    if len(q) > s.max_question_chars:
        raise ValidationFailed(f"Question must be at most {s.max_question_chars} characters")
    return q


def validate_document_id(document_id: str) -> str:
    if not _DOC_ID_RE.match(document_id):
        raise ValidationFailed("Invalid document id")
    return document_id


def validate_user_id(user_id: str) -> str:
    if not _USER_ID_RE.match(user_id):
        raise ValidationFailed("Invalid user")
    return user_id


def looks_like_pdf(first_bytes: bytes) -> bool:
    return first_bytes.startswith(PDF_MAGIC)


def build_s3_key(user_id: str, document_id: str) -> str:
    """Server-generated key; the client never influences any part of it."""
    return f"uploads/{validate_user_id(user_id)}/{validate_document_id(document_id)}.pdf"


def document_id_from_key(s3_key: str) -> str | None:
    parsed = owner_and_document_from_key(s3_key)
    return parsed[1] if parsed else None


def owner_and_document_from_key(s3_key: str) -> tuple[str, str] | None:
    """(owner, documentId) from a key built by build_s3_key; None for any other key."""
    m = _KEY_RE.match(s3_key)
    return (m.group(1), m.group(2)) if m else None
