"""Service wiring. Phase 2 will add the boto3-backed factory; tests inject fakes."""

from __future__ import annotations

import os
from collections.abc import Mapping
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


def build_services(env: Mapping[str, str] | None = None) -> Services:
    """Create boto3-backed services from environment variables (set by Terraform)."""
    import boto3
    from botocore.config import Config

    from .adapters.bedrock import BedrockKnowledgeBase
    from .adapters.dynamodb import DynamoDocumentRepository
    from .adapters.s3 import S3Storage

    e = os.environ if env is None else env
    settings = Settings.from_env()
    cfg = Config(retries={"mode": "standard", "max_attempts": 3}, signature_version="s3v4")
    bucket = e["DOCUMENTS_BUCKET"]
    repo = DynamoDocumentRepository(boto3.client("dynamodb", config=cfg), e["TABLE_NAME"])
    storage = S3Storage(boto3.client("s3", config=cfg), bucket)
    kb = BedrockKnowledgeBase(
        boto3.client("bedrock-agent", config=cfg),
        boto3.client("bedrock-agent-runtime", config=cfg),
        knowledge_base_id=e["KNOWLEDGE_BASE_ID"],
        data_source_id=e["DATA_SOURCE_ID"],
        bucket=bucket,
        model_arn=e["MODEL_ARN"],
    )
    return Services(
        documents=DocumentService(repo, storage, kb, settings),
        chat=ChatService(repo, kb, settings),
        settings=settings,
    )


def get_services() -> Services:
    global _services
    if _services is None:
        _services = build_services()  # cached across warm Lambda invocations
    return _services
