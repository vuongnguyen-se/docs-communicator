"""Adapter tests: exact AWS requests checked offline with botocore's Stubber.

No network and fake credentials: nothing here can touch a real AWS account.
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Iterator

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from clouddocs.adapters.dynamodb_repo import DynamoDocumentRepository, from_item, to_item
from clouddocs.adapters.pending_kb import PendingKnowledgeBase
from clouddocs.adapters.s3_storage import S3ObjectStorage
from clouddocs.errors import Conflict
from clouddocs.models import Document, IndexState
from clouddocs.models import DocumentStatus as S

REGION = "ap-southeast-1"
TABLE = "Documents"
BUCKET = "docs-bucket"
NOW = "2026-01-02T00:00:00+00:00"


def _client(service: str):  # type: ignore[no-untyped-def]
    return boto3.client(
        service,
        region_name=REGION,
        aws_access_key_id="AKIDTEST",
        aws_secret_access_key="secret",
        config=boto3.session.Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def _doc(owner: str = "user-a", doc_id: str = "doc_" + "a" * 32, **kw: object) -> Document:
    base: dict[str, object] = dict(
        document_id=doc_id,
        owner_id=owner,
        filename="tài-liệu.pdf",
        s3_key=f"uploads/{owner}/{doc_id}.pdf",
        file_size=1234,
        content_type="application/pdf",
        status=S.PENDING_UPLOAD,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    base.update(kw)
    return Document(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------- DynamoDB


@pytest.fixture
def ddb() -> Iterator[tuple[DynamoDocumentRepository, Stubber]]:
    client = _client("dynamodb")
    with Stubber(client) as stub:
        yield DynamoDocumentRepository(client, TABLE, now=lambda: NOW), stub
        stub.assert_no_pending_responses()


def test_item_round_trip_keeps_unicode_and_nulls() -> None:
    doc = _doc(error_code=None)
    item = to_item(doc)
    assert item["PK"] == {"S": "USER#user-a"} and item["SK"] == {"S": "DOC#" + doc.document_id}
    assert item["errorCode"] == {"NULL": True}
    assert from_item(item) == doc


def test_put_never_overwrites(ddb: tuple[DynamoDocumentRepository, Stubber]) -> None:
    repo, stub = ddb
    doc = _doc()
    stub.add_response(
        "put_item",
        {},
        {
            "TableName": TABLE,
            "Item": to_item(doc),
            "ConditionExpression": "attribute_not_exists(PK)",
        },
    )
    repo.put(doc)


def test_put_duplicate_is_conflict(ddb: tuple[DynamoDocumentRepository, Stubber]) -> None:
    repo, stub = ddb
    stub.add_client_error("put_item", service_error_code="ConditionalCheckFailedException")
    with pytest.raises(Conflict):
        repo.put(_doc())


def test_get_is_scoped_by_owner_key(ddb: tuple[DynamoDocumentRepository, Stubber]) -> None:
    repo, stub = ddb
    doc = _doc()
    stub.add_response(
        "get_item",
        {"Item": to_item(doc)},
        {
            "TableName": TABLE,
            "Key": {"PK": {"S": "USER#user-a"}, "SK": {"S": "DOC#" + doc.document_id}},
            "ConsistentRead": True,
        },
    )
    assert repo.get("user-a", doc.document_id) == doc


def test_get_missing_returns_none(ddb: tuple[DynamoDocumentRepository, Stubber]) -> None:
    repo, stub = ddb
    stub.add_response("get_item", {})
    assert repo.get("user-b", "doc_" + "b" * 32) is None


def test_list_queries_never_scans_paginates_and_sorts_newest_first(
    ddb: tuple[DynamoDocumentRepository, Stubber],
) -> None:
    repo, stub = ddb
    old = _doc(doc_id="doc_" + "1" * 32, created_at="2026-01-01T00:00:00+00:00")
    new = _doc(doc_id="doc_" + "2" * 32, created_at="2026-01-03T00:00:00+00:00")
    expected = {
        "TableName": TABLE,
        "KeyConditionExpression": "PK = :pk AND begins_with(SK, :doc)",
        "ExpressionAttributeValues": {":pk": {"S": "USER#user-a"}, ":doc": {"S": "DOC#"}},
        "ConsistentRead": True,
    }
    last_key = {"PK": {"S": "USER#user-a"}, "SK": {"S": "DOC#x"}}
    stub.add_response("query", {"Items": [to_item(old)], "LastEvaluatedKey": last_key}, expected)
    stub.add_response(
        "query", {"Items": [to_item(new)]}, {**expected, "ExclusiveStartKey": last_key}
    )
    assert [d.document_id for d in repo.list("user-a")] == [new.document_id, old.document_id]


def test_update_status_is_conditional(ddb: tuple[DynamoDocumentRepository, Stubber]) -> None:
    repo, stub = ddb
    doc = _doc()
    updated = to_item(doc.model_copy(update={"status": S.UPLOADED, "updated_at": NOW}))
    stub.add_response(
        "update_item",
        {"Attributes": updated},
        {
            "TableName": TABLE,
            "Key": {"PK": {"S": "USER#user-a"}, "SK": {"S": "DOC#" + doc.document_id}},
            "UpdateExpression": "SET #status = :new, updatedAt = :now, errorCode = :err",
            "ConditionExpression": "#status = :expected",
            "ExpressionAttributeNames": {"#status": "status"},
            "ExpressionAttributeValues": {
                ":new": {"S": "UPLOADED"},
                ":expected": {"S": "PENDING_UPLOAD"},
                ":now": {"S": NOW},
                ":err": {"NULL": True},
            },
            "ReturnValues": "ALL_NEW",
        },
    )
    result = repo.update_status("user-a", doc.document_id, S.PENDING_UPLOAD, S.UPLOADED)
    assert result.status == S.UPLOADED and result.updated_at == NOW


def test_update_status_race_is_conflict(ddb: tuple[DynamoDocumentRepository, Stubber]) -> None:
    repo, stub = ddb
    stub.add_client_error("update_item", service_error_code="ConditionalCheckFailedException")
    with pytest.raises(Conflict):
        repo.update_status("user-a", "doc_" + "a" * 32, S.PENDING_UPLOAD, S.UPLOADED)


def test_update_status_rejects_illegal_transition_before_calling_aws(
    ddb: tuple[DynamoDocumentRepository, Stubber],
) -> None:
    repo, _ = ddb  # no stubbed response: any AWS call would fail the test
    with pytest.raises(Conflict):
        repo.update_status("user-a", "doc_" + "a" * 32, S.READY, S.PENDING_UPLOAD)


def test_delete(ddb: tuple[DynamoDocumentRepository, Stubber]) -> None:
    repo, stub = ddb
    stub.add_response(
        "delete_item",
        {},
        {"TableName": TABLE, "Key": {"PK": {"S": "USER#user-a"}, "SK": {"S": "DOC#x"}}},
    )
    repo.delete("user-a", "x")


# ---------------------------------------------------------------- S3


def test_presigned_post_pins_key_type_and_size() -> None:
    storage = S3ObjectStorage(_client("s3"), BUCKET)
    key = "uploads/user-a/doc_" + "a" * 32 + ".pdf"
    post = storage.create_presigned_post(key, "application/pdf", 10 * 1024 * 1024, 300)

    assert post.url == f"https://{BUCKET}.s3.{REGION}.amazonaws.com/"
    assert post.fields["key"] == key and post.fields["Content-Type"] == "application/pdf"
    policy = json.loads(base64.b64decode(post.fields["policy"]))
    conditions = policy["conditions"]
    assert {"bucket": BUCKET} in conditions
    assert {"key": key} in conditions
    assert {"Content-Type": "application/pdf"} in conditions
    assert ["content-length-range", 1, 10 * 1024 * 1024] in conditions


@pytest.fixture
def s3() -> Iterator[tuple[S3ObjectStorage, Stubber]]:
    client = _client("s3")
    with Stubber(client) as stub:
        yield S3ObjectStorage(client, BUCKET), stub
        stub.assert_no_pending_responses()


def test_head_reads_size_and_first_bytes(s3: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stub = s3
    stub.add_response("head_object", {"ContentLength": 2048}, {"Bucket": BUCKET, "Key": "k"})
    body = StreamingBody(io.BytesIO(b"%PDF-1.7"), 8)
    stub.add_response(
        "get_object", {"Body": body}, {"Bucket": BUCKET, "Key": "k", "Range": "bytes=0-7"}
    )
    info = storage.head("k")
    assert info is not None and info.size == 2048 and info.first_bytes == b"%PDF-1.7"


def test_head_missing_object_is_none(s3: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stub = s3
    stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
    assert storage.head("missing") is None


def test_head_other_errors_propagate(s3: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stub = s3
    stub.add_client_error("head_object", service_error_code="AccessDenied", http_status_code=403)
    with pytest.raises(Exception, match="AccessDenied"):
        storage.head("k")


def test_delete_object(s3: tuple[S3ObjectStorage, Stubber]) -> None:
    storage, stub = s3
    stub.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": ANY})
    storage.delete("k")


# ---------------------------------------------------------------- Pending KB


def test_pending_kb_never_reports_indexed() -> None:
    kb = PendingKnowledgeBase()
    kb.ingest("k", "user-a", "doc")
    assert kb.index_state("k") == IndexState.IN_PROGRESS
    assert kb.query("anything").references == []
