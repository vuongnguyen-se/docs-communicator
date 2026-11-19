"""Service wiring.

In Lambda, services are built once per container (on first request) from
environment variables set by the CDK stack, and reused across invocations.
Tests inject in-memory fakes with set_services().
"""

from __future__ import annotations

import os
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
    global _services
    if _services is None:
        _services = build_services_from_env()
    return _services


def build_services_from_env() -> Services:
    # Imported here so unit tests never need AWS libraries or credentials.
    import boto3
    from botocore.config import Config

    from .adapters.dynamodb_repo import DynamoDocumentRepository
    from .adapters.pending_kb import PendingKnowledgeBase
    from .adapters.s3_storage import S3ObjectStorage

    region = os.environ["AWS_REGION"]  # set automatically by Lambda
    common = Config(
        retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=2, read_timeout=5
    )
    dynamodb = boto3.client("dynamodb", region_name=region, config=common)
    # Regional virtual-hosted URLs: https://<bucket>.s3.<region>.amazonaws.com/
    s3_config = common.merge(Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    s3 = boto3.client("s3", region_name=region, config=s3_config)

    settings = Settings.from_env()
    repo = DynamoDocumentRepository(dynamodb, os.environ["DOCUMENTS_TABLE"])
    storage = S3ObjectStorage(s3, os.environ["DOCUMENTS_BUCKET"])
    kb = PendingKnowledgeBase()  # Phase 3 replaces this with the Bedrock adapter
    return Services(
        documents=DocumentService(repo, storage, kb, settings),
        chat=ChatService(repo, kb, settings),
        settings=settings,
    )
