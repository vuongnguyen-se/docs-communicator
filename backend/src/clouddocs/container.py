"""Service wiring. Phase 2 will add the boto3-backed factory; tests inject fakes."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .services.chat import ChatService
from .services.documents import DocumentService


@dataclass(frozen=True)
class Services:
    documents: DocumentService
    chat: ChatService
    settings: Settings


_services: Services | None = None


def set_services(services: Services | None) -> None:
    global _services
    _services = services


def get_services() -> Services:
    if _services is None:
        raise RuntimeError("AWS adapters are not wired yet (Phase 2)")
    return _services
