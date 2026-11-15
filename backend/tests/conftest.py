from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from clouddocs.config import Settings
from clouddocs.container import Services, set_services
from clouddocs.services.chat import ChatService
from clouddocs.services.documents import DocumentService

from .fakes import FakeKB, FakeRepo, FakeStorage

USER_A = "user-a-sub"
USER_B = "user-b-sub"


class Env:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)
        self.repo = FakeRepo(now=lambda: self.now.isoformat())
        self.storage, self.kb = FakeStorage(), FakeKB()
        self.settings = Settings(max_documents=3)
        counter = itertools.count(1)
        self.docs = DocumentService(
            self.repo,
            self.storage,
            self.kb,
            self.settings,
            now=lambda: self.now.isoformat(),
            new_id=lambda: f"doc_{next(counter):032x}",
        )
        self.chat = ChatService(self.repo, self.kb, self.settings)

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)

    def upload_pdf(self, user: str = USER_A, name: str = "notes.pdf", data: bytes | None = None):
        from clouddocs.models import UploadUrlRequest

        payload = data if data is not None else b"%PDF-1.7 hello"
        doc, _ = self.docs.request_upload(
            user, UploadUrlRequest(filename=name, contentType="application/pdf", size=len(payload))
        )
        self.storage.objects[doc.s3_key] = payload
        return doc


@pytest.fixture
def env() -> Iterator[Env]:
    e = Env()
    set_services(Services(documents=e.docs, chat=e.chat, settings=e.settings))
    yield e
    set_services(None)


def api_event(route: str, user: str | None = USER_A, body: Any = None, path_id: str | None = None):
    event: dict[str, Any] = {
        "routeKey": route,
        "requestContext": {"requestId": "req-1"},
        "pathParameters": {"id": path_id} if path_id else None,
        "body": json.dumps(body) if body is not None else None,
    }
    if user is not None:
        event["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": user}}}
    return event
