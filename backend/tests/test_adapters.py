"""Adapter tests using botocore's Stubber: requests are validated against the real service
models, but nothing touches the network and no credentials are needed."""

from __future__ import annotations

import io
from typing import Any

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from clouddocs.adapters.bedrock import BedrockKnowledgeBase, map_document_status
from clouddocs.adapters.dynamodb import DynamoDocumentRepository
from clouddocs.adapters.s3 import S3Storage
from clouddocs.errors import Conflict, UpstreamUnavailable
from clouddocs.models import Document, DocumentStatus, IndexState

REGION = "ap-southeast-1"
BUCKET = "docs-bucket"
KEY = "users/u1/doc_1.pdf"
_CFG = Config(retries={"max_attempts": 1})


def client(service: str) -> Any:
    return boto3.client(
        service,
        region_name=REGION,
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106 - dummy value, never a real credential
        config=_CFG,
    )


def make_doc(status: DocumentStatus = DocumentStatus.PENDING_UPLOAD, **kw: Any) -> Document:
    base: dict[str, Any] = {
        "document_id": "doc_1",
        "owner_id": "u1",
        "filename": "a.pdf",
        "s3_key": KEY,
        "file_size": 10,
        "content_type": "application/pdf",
        "status": status,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    return Document(**{**base, **kw})


# ---- S3 ------------------------------------------------------------------
def test_presigned_post_enforces_size_and_type_policy() -> None:
    import base64
    import json

    s3 = S3Storage(client("s3"), BUCKET)
    post = s3.create_presigned_post(KEY, "application/pdf", 1000, 300)
    assert post.fields["key"] == KEY
    assert post.fields["Content-Type"] == "application/pdf"
    policy = json.loads(base64.b64decode(post.fields["policy"]))
    assert ["content-length-range", 1, 1000] in policy["conditions"]
    assert {"Content-Type": "application/pdf"} in policy["conditions"]
    assert {"bucket": BUCKET} in policy["conditions"]


def test_head_returns_size_and_first_bytes() -> None:
    c = client("s3")
    data = b"%PDF-1.7"
    with Stubber(c) as st:
        st.add_response("head_object", {"ContentLength": 5000}, {"Bucket": BUCKET, "Key": KEY})
        st.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(data), len(data))},
            {"Bucket": BUCKET, "Key": KEY, "Range": "bytes=0-7"},
        )
        info = S3Storage(c, BUCKET).head(KEY)
    assert info is not None and info.size == 5000 and info.first_bytes == data


def test_head_missing_object_returns_none() -> None:
    c = client("s3")
    with Stubber(c) as st:
        st.add_client_error("head_object", "404", http_status_code=404)
        assert S3Storage(c, BUCKET).head(KEY) is None


def test_s3_throttle_maps_to_upstream_unavailable() -> None:
    c = client("s3")
    with Stubber(c) as st:
        st.add_client_error("delete_object", "SlowDown", http_status_code=503)
        with pytest.raises(UpstreamUnavailable):
            S3Storage(c, BUCKET).delete(KEY)


def test_s3_delete_calls_delete_object() -> None:
    c = client("s3")
    with Stubber(c) as st:
        st.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": KEY})
        S3Storage(c, BUCKET).delete(KEY)
        st.assert_no_pending_responses()


# ---- DynamoDB ------------------------------------------------------------
def repo(c: Any) -> DynamoDocumentRepository:
    return DynamoDocumentRepository(c, "tbl", now=lambda: "2026-02-02T00:00:00+00:00")


def test_put_get_roundtrip_uses_owner_scoped_key() -> None:
    from clouddocs.adapters.dynamodb import to_item

    c = client("dynamodb")
    doc = make_doc(error_code="X")
    with Stubber(c) as st:
        st.add_response("put_item", {}, {"TableName": "tbl", "Item": to_item(doc)})
        repo(c).put(doc)
        st.add_response(
            "get_item",
            {"Item": to_item(doc)},
            {
                "TableName": "tbl",
                "Key": {"PK": {"S": "USER#u1"}, "SK": {"S": "DOC#doc_1"}},
                "ConsistentRead": True,
            },
        )
        assert repo(c).get("u1", "doc_1") == doc


def test_get_missing_returns_none() -> None:
    c = client("dynamodb")
    with Stubber(c) as st:
        st.add_response("get_item", {})
        assert repo(c).get("u1", "doc_1") is None


def test_list_paginates_and_sorts() -> None:
    from clouddocs.adapters.dynamodb import to_item

    c = client("dynamodb")
    d1 = make_doc(document_id="doc_1", created_at="2026-01-02")
    d2 = make_doc(document_id="doc_2", created_at="2026-01-01")
    with Stubber(c) as st:
        st.add_response(
            "query",
            {"Items": [to_item(d1)], "LastEvaluatedKey": {"PK": {"S": "x"}, "SK": {"S": "y"}}},
        )
        st.add_response("query", {"Items": [to_item(d2)]})
        got = repo(c).list("u1")
    assert [d.document_id for d in got] == ["doc_2", "doc_1"]


def test_update_status_is_conditional_on_expected_status() -> None:
    from clouddocs.adapters.dynamodb import to_item

    c = client("dynamodb")
    updated = make_doc(DocumentStatus.UPLOADED, updated_at="2026-02-02T00:00:00+00:00")
    with Stubber(c) as st:
        st.add_response(
            "update_item",
            {"Attributes": to_item(updated)},
            {
                "TableName": "tbl",
                "Key": {"PK": {"S": "USER#u1"}, "SK": {"S": "DOC#doc_1"}},
                "UpdateExpression": "SET #s = :new, updatedAt = :now REMOVE errorCode",
                "ConditionExpression": "#s = :expected",
                "ExpressionAttributeNames": {"#s": "status"},
                "ExpressionAttributeValues": {
                    ":expected": {"S": "PENDING_UPLOAD"},
                    ":new": {"S": "UPLOADED"},
                    ":now": {"S": "2026-02-02T00:00:00+00:00"},
                },
                "ReturnValues": "ALL_NEW",
            },
        )
        got = repo(c).update_status(
            "u1", "doc_1", DocumentStatus.PENDING_UPLOAD, DocumentStatus.UPLOADED
        )
    assert got.status == DocumentStatus.UPLOADED


def test_update_status_conflict_on_failed_condition() -> None:
    c = client("dynamodb")
    with Stubber(c) as st:
        st.add_client_error("update_item", "ConditionalCheckFailedException")
        with pytest.raises(Conflict):
            repo(c).update_status(
                "u1", "doc_1", DocumentStatus.PENDING_UPLOAD, DocumentStatus.UPLOADED
            )


def test_update_status_rejects_illegal_transition_without_calling_aws() -> None:
    c = client("dynamodb")
    with Stubber(c) as st:  # no responses queued: any call would fail
        with pytest.raises(Exception) as ei:
            repo(c).update_status("u1", "doc_1", DocumentStatus.READY, DocumentStatus.UPLOADED)
        assert not isinstance(ei.value, AssertionError)
        st.assert_no_pending_responses()


def test_update_status_sets_error_code() -> None:
    from clouddocs.adapters.dynamodb import to_item

    c = client("dynamodb")
    failed = make_doc(DocumentStatus.FAILED, error_code="INVALID_FILE")
    with Stubber(c) as st:
        st.add_response("update_item", {"Attributes": to_item(failed)})
        got = repo(c).update_status(
            "u1", "doc_1", DocumentStatus.PENDING_UPLOAD, DocumentStatus.FAILED, "INVALID_FILE"
        )
    assert got.error_code == "INVALID_FILE"


def test_dynamo_delete_and_connection_error() -> None:
    c = client("dynamodb")
    with Stubber(c) as st:
        st.add_response("delete_item", {})
        repo(c).delete("u1", "doc_1")
        st.assert_no_pending_responses()
    c2 = client("dynamodb")
    c2.put_item = lambda **_: (_ for _ in ()).throw(  # type: ignore[method-assign]
        EndpointConnectionError(endpoint_url="x")
    )
    with pytest.raises(UpstreamUnavailable):
        repo(c2).put(make_doc())


# ---- Bedrock KB ----------------------------------------------------------
def kb(agent: Any, rt: Any) -> BedrockKnowledgeBase:
    return BedrockKnowledgeBase(
        agent,
        rt,
        knowledge_base_id="KB12345678",
        data_source_id="DS12345678",
        bucket=BUCKET,
        model_arn="arn:aws:bedrock:ap-southeast-1::foundation-model/test",
    )


URI = f"s3://{BUCKET}/{KEY}"


def test_ingest_sends_only_s3_location_no_inline_metadata() -> None:
    agent = client("bedrock-agent")
    seen: dict[str, Any] = {}

    def capture(params: dict[str, Any], **_: Any) -> None:
        seen.update(params)

    agent.meta.events.register("provide-client-params.bedrock-agent.*", capture)
    with Stubber(agent) as st:
        st.add_response("ingest_knowledge_base_documents", {"documentDetails": []})
        kb(agent, client("bedrock-agent-runtime")).ingest(KEY, "u1", "doc_1")
        st.assert_no_pending_responses()
    assert seen["knowledgeBaseId"] == "KB12345678"
    assert seen["dataSourceId"] == "DS12345678"
    doc = seen["documents"][0]
    assert doc["content"] == {
        "dataSourceType": "S3",
        "s3": {"s3Location": {"uri": URI}},
    }
    assert "metadata" not in doc  # S3 data sources reject inline metadata


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("INDEXED", IndexState.INDEXED),
        ("PENDING", IndexState.IN_PROGRESS),
        ("STARTING", IndexState.IN_PROGRESS),
        ("IN_PROGRESS", IndexState.IN_PROGRESS),
        ("FAILED", IndexState.FAILED),
        ("PARTIALLY_INDEXED", IndexState.FAILED),
        ("METADATA_PARTIALLY_INDEXED", IndexState.FAILED),
        ("NOT_FOUND", IndexState.NOT_FOUND),
        ("SOMETHING_NEW", IndexState.FAILED),
    ],
)
def test_status_mapping(status: str, expected: IndexState) -> None:
    assert map_document_status(status) == expected


def test_index_state_reads_document_status() -> None:
    agent = client("bedrock-agent")
    with Stubber(agent) as st:
        st.add_response(
            "get_knowledge_base_documents",
            {
                "documentDetails": [
                    {
                        "knowledgeBaseId": "KB12345678",
                        "dataSourceId": "DS12345678",
                        "status": "INDEXED",
                        "identifier": {"dataSourceType": "S3", "s3": {"uri": URI}},
                    }
                ]
            },
        )
        assert kb(agent, client("bedrock-agent-runtime")).index_state(KEY) == IndexState.INDEXED


def test_index_state_empty_details_is_not_found() -> None:
    agent = client("bedrock-agent")
    with Stubber(agent) as st:
        st.add_response("get_knowledge_base_documents", {"documentDetails": []})
        assert kb(agent, client("bedrock-agent-runtime")).index_state(KEY) == IndexState.NOT_FOUND


def test_kb_delete_and_throttling() -> None:
    agent = client("bedrock-agent")
    with Stubber(agent) as st:
        st.add_response("delete_knowledge_base_documents", {"documentDetails": []})
        kb(agent, client("bedrock-agent-runtime")).delete(KEY)
        st.add_client_error("delete_knowledge_base_documents", "ThrottlingException")
        with pytest.raises(UpstreamUnavailable):
            kb(agent, client("bedrock-agent-runtime")).delete(KEY)


def test_query_parses_answer_and_references() -> None:
    rt = client("bedrock-agent-runtime")
    with Stubber(rt) as st:
        st.add_response(
            "retrieve_and_generate",
            {
                "sessionId": "sess-1",
                "output": {"text": "SQS queues, SNS fans out."},
                "citations": [
                    {
                        "retrievedReferences": [
                            {
                                "content": {"text": "passage"},
                                "location": {"type": "S3", "s3Location": {"uri": URI}},
                            }
                        ]
                    }
                ],
            },
            {
                "input": {"text": "q?"},
                "retrieveAndGenerateConfiguration": {
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": "KB12345678",
                        "modelArn": "arn:aws:bedrock:ap-southeast-1::foundation-model/test",
                    },
                },
            },
        )
        result = kb(client("bedrock-agent"), rt).query("q?")
    assert result.answer.startswith("SQS")
    assert [(r.s3_uri, r.text) for r in result.references] == [(URI, "passage")]


def test_query_throttling_maps_to_upstream_unavailable() -> None:
    rt = client("bedrock-agent-runtime")
    with Stubber(rt) as st:
        st.add_client_error("retrieve_and_generate", "ThrottlingException")
        with pytest.raises(UpstreamUnavailable):
            kb(client("bedrock-agent"), rt).query("q?")


# ---- wiring --------------------------------------------------------------
def test_build_services_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from clouddocs.container import build_services

    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    svc = build_services(
        {
            "DOCUMENTS_BUCKET": BUCKET,
            "TABLE_NAME": "tbl",
            "KNOWLEDGE_BASE_ID": "KB12345678",
            "DATA_SOURCE_ID": "DS12345678",
            "MODEL_ARN": "arn:aws:bedrock:ap-southeast-1::foundation-model/test",
        }
    )
    assert svc.documents is not None and svc.chat is not None
