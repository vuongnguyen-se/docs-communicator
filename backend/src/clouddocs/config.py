"""Runtime configuration. Values come from environment variables set by the CDK stack."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_file_bytes: int = 10 * 1024 * 1024
    max_documents: int = 5
    max_question_chars: int = 2000
    upload_url_ttl_seconds: int = 300
    max_filename_chars: int = 200

    @classmethod
    def from_env(cls) -> Settings:
        d = cls()
        return cls(
            max_file_bytes=int(os.environ.get("MAX_FILE_BYTES", d.max_file_bytes)),
            max_documents=int(os.environ.get("MAX_DOCUMENTS", d.max_documents)),
            max_question_chars=int(os.environ.get("MAX_QUESTION_CHARS", d.max_question_chars)),
            upload_url_ttl_seconds=int(
                os.environ.get("UPLOAD_URL_TTL_SECONDS", d.upload_url_ttl_seconds)
            ),
        )
