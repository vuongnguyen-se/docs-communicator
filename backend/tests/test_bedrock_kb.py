"""Bedrock Knowledge Base adapter: exact requests checked offline with botocore's Stubber."""

from __future__ import annotations

import json
from collections.abc import Iterator

import boto3
import pytest
from botocore.stub import Stubber

from clouddocs.adapters.bedrock_kb import BedrockKnowledgeBase, IngestRejected, metadata_document
from clouddocs.models import IndexState

REGION = "ap-southeast-1"
BUCKET = "docs-bucket"
KB, DS = "KB12345678", "DS12345678"
KEY = "uploads/user-a/doc_" + "a" * 32 + ".pdf"
URI = f"s3://{BUCKET}/{KEY}"
IDENT = [{"dataSourceType": "S3", "s3": {"uri": URI}}]


def _client(service: str):  # type: ignore[no-untyped-def]
    return boto3.client(
        service, region_name=REGION, aws_access_key_id="AKIDTEST", aws_secret_access_key="secret"
    )


@pytest.fixture
def env() -> Iterator[tuple[BedrockKnowledgeBase, Stubber, Stubber]]:
    agent, s3 = _client("bedrock-agent"), _client("s3")
    with Stubber(agent) as a, Stubber(s3) as s:
        kb = BedrockKnowledgeBase(agent, s3, knowledge_base_id=KB, data_source_id=DS, bucket=BUCKET)
        yield kb, a, s
        a.assert_no_pending_responses()
        s.assert_no_pending_responses()


def _details(status: str) -> dict[str, object]:
    return {
        "documentDetails": [
            {
                "knowledgeBaseId": KB,
                "dataSourceId": DS,
                "status": status,
                "identifier": {"dataSourceType": "S3", "s3": {"uri": URI}},
            }
        ]
    }


def test_metadata_document_shape() -> None:
    assert json.loads(metadata_document("user-a", "doc_1")) == {
        "metadataAttributes": {"userId": "user-a", "documentId": "doc_1"}
    }


def test_ingest_writes_sidecar_then_ingests_with_s3_locations(env) -> None:  # type: ignore[no-untyped-def]
    kb, agent, s3 = env
    s3.add_response(
        "put_object",
        {},
        {
            "Bucket": BUCKET,
            "Key": KEY + ".metadata.json",
            "Body": metadata_document("user-a", "doc_x"),
            "ContentType": "application/json",
        },
    )
    agent.add_response(
        "ingest_knowledge_base_documents",
        _details("STARTING"),
        {
            "knowledgeBaseId": KB,
            "dataSourceId": DS,
            "documents": [
                {
                    "content": {"dataSourceType": "S3", "s3": {"s3Location": {"uri": URI}}},
                    "metadata": {
                        "type": "S3_LOCATION",
                        "s3Location": {"uri": URI + ".metadata.json"},
                    },
                }
            ],
        },
    )
    kb.ingest(KEY, "user-a", "doc_x")


def test_ingest_rejected_raises(env) -> None:  # type: ignore[no-untyped-def]
    kb, agent, s3 = env
    s3.add_response("put_object", {})
    agent.add_response("ingest_knowledge_base_documents", _details("FAILED"))
    with pytest.raises(IngestRejected):
        kb.ingest(KEY, "user-a", "doc_x")


@pytest.mark.parametrize(
    ("bedrock_status", "expected"),
    [
        ("STARTING", IndexState.IN_PROGRESS),
        ("IN_PROGRESS", IndexState.IN_PROGRESS),
        ("PENDING", IndexState.IN_PROGRESS),
        ("INDEXED", IndexState.INDEXED),
        ("FAILED", IndexState.FAILED),
        # Never READY with missing metadata: it could escape the per-user filter.
        ("METADATA_PARTIALLY_INDEXED", IndexState.FAILED),
        ("PARTIALLY_INDEXED", IndexState.FAILED),
        ("NOT_FOUND", IndexState.NOT_FOUND),
        ("DELETE_IN_PROGRESS", IndexState.IN_PROGRESS),
    ],
)
def test_index_state_mapping(env, bedrock_status: str, expected: IndexState) -> None:  # type: ignore[no-untyped-def]
    kb, agent, _ = env
    agent.add_response(
        "get_knowledge_base_documents",
        _details(bedrock_status),
        {"knowledgeBaseId": KB, "dataSourceId": DS, "documentIdentifiers": IDENT},
    )
    assert kb.index_state(KEY) == expected


def test_index_state_with_no_details_is_not_found(env) -> None:  # type: ignore[no-untyped-def]
    kb, agent, _ = env
    agent.add_response("get_knowledge_base_documents", {"documentDetails": []})
    assert kb.index_state(KEY) == IndexState.NOT_FOUND


def test_delete_removes_from_index_and_sidecar(env) -> None:  # type: ignore[no-untyped-def]
    kb, agent, s3 = env
    agent.add_response(
        "delete_knowledge_base_documents",
        _details("DELETING"),
        {"knowledgeBaseId": KB, "dataSourceId": DS, "documentIdentifiers": IDENT},
    )
    s3.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": KEY + ".metadata.json"})
    kb.delete(KEY)


def test_query_refuses_until_phase4_filter_exists(env) -> None:  # type: ignore[no-untyped-def]
    kb, _, _ = env
    with pytest.raises(NotImplementedError):
        kb.query("anything")


def test_container_selects_bedrock_adapter_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from clouddocs import container
    from clouddocs.adapters.pending_kb import PendingKnowledgeBase

    for k, v in {
        "AWS_REGION": REGION,
        "AWS_ACCESS_KEY_ID": "AKIDTEST",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "DOCUMENTS_TABLE": "t",
        "DOCUMENTS_BUCKET": BUCKET,
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("KNOWLEDGE_BASE_ID", raising=False)
    assert isinstance(container.build_services_from_env().documents._kb, PendingKnowledgeBase)

    monkeypatch.setenv("KNOWLEDGE_BASE_ID", KB)
    monkeypatch.setenv("DATA_SOURCE_ID", DS)
    assert isinstance(container.build_services_from_env().documents._kb, BedrockKnowledgeBase)
