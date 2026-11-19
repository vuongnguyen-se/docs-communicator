"""DynamoDB implementation of DocumentRepository (see DATABASE_DESIGN.md).

Key design: PK = "USER#<sub>", SK = "DOC#<documentId>". Every read and write
includes the owner in the key, so one user can never address another user's
item. Status changes are conditional writes (compare-and-set) so concurrent
requests cannot both move a document.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError

from ..errors import Conflict
from ..models import Document, DocumentStatus
from ..status import ensure_transition

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient
    from mypy_boto3_dynamodb.type_defs import AttributeValueTypeDef

Item = dict[str, "AttributeValueTypeDef"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def pk(owner_id: str) -> str:
    return f"USER#{owner_id}"


def sk(document_id: str) -> str:
    return f"DOC#{document_id}"


def _s(value: str | None) -> AttributeValueTypeDef:
    return {"NULL": True} if value is None else {"S": value}


def to_item(doc: Document) -> Item:
    return {
        "PK": {"S": pk(doc.owner_id)},
        "SK": {"S": sk(doc.document_id)},
        "documentId": {"S": doc.document_id},
        "userId": {"S": doc.owner_id},
        "filename": {"S": doc.filename},
        "s3Key": {"S": doc.s3_key},
        "contentType": {"S": doc.content_type},
        "fileSize": {"N": str(doc.file_size)},
        "status": {"S": doc.status.value},
        "createdAt": {"S": doc.created_at},
        "updatedAt": {"S": doc.updated_at},
        "ingestionJobId": _s(doc.ingestion_job_id),
        "errorCode": _s(doc.error_code),
    }


def _opt(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    return value["S"] if value and "S" in value else None


def from_item(item: dict[str, Any]) -> Document:
    return Document(
        document_id=item["documentId"]["S"],
        owner_id=item["userId"]["S"],
        filename=item["filename"]["S"],
        s3_key=item["s3Key"]["S"],
        content_type=item["contentType"]["S"],
        file_size=int(item["fileSize"]["N"]),
        status=DocumentStatus(item["status"]["S"]),
        created_at=item["createdAt"]["S"],
        updated_at=item["updatedAt"]["S"],
        ingestion_job_id=_opt(item, "ingestionJobId"),
        error_code=_opt(item, "errorCode"),
    )


def _is_conditional_failure(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


class DynamoDocumentRepository:
    def __init__(
        self, client: DynamoDBClient, table_name: str, now: Callable[[], str] = _now
    ) -> None:
        self._db, self._table, self._now = client, table_name, now

    def put(self, doc: Document) -> None:
        try:
            self._db.put_item(
                TableName=self._table,
                Item=to_item(doc),
                ConditionExpression="attribute_not_exists(PK)",  # never overwrite
            )
        except ClientError as exc:
            if _is_conditional_failure(exc):
                raise Conflict("Document already exists") from exc
            raise

    def get(self, owner_id: str, document_id: str) -> Document | None:
        resp = self._db.get_item(
            TableName=self._table,
            Key={"PK": {"S": pk(owner_id)}, "SK": {"S": sk(document_id)}},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        return from_item(item) if item else None

    def list(self, owner_id: str) -> list[Document]:
        docs: list[Document] = []
        kwargs: dict[str, Any] = {
            "TableName": self._table,
            "KeyConditionExpression": "PK = :pk AND begins_with(SK, :doc)",
            "ExpressionAttributeValues": {":pk": {"S": pk(owner_id)}, ":doc": {"S": "DOC#"}},
            "ConsistentRead": True,
        }
        while True:
            resp = self._db.query(**kwargs)
            docs.extend(from_item(i) for i in resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return sorted(docs, key=lambda d: d.created_at, reverse=True)  # newest first

    def update_status(
        self,
        owner_id: str,
        document_id: str,
        expected: DocumentStatus,
        new: DocumentStatus,
        error_code: str | None = None,
    ) -> Document:
        ensure_transition(expected, new)
        try:
            resp = self._db.update_item(
                TableName=self._table,
                Key={"PK": {"S": pk(owner_id)}, "SK": {"S": sk(document_id)}},
                UpdateExpression="SET #status = :new, updatedAt = :now, errorCode = :err",
                ConditionExpression="#status = :expected",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":new": {"S": new.value},
                    ":expected": {"S": expected.value},
                    ":now": {"S": self._now()},
                    ":err": _s(error_code),
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _is_conditional_failure(exc):
                raise Conflict("Document status changed concurrently") from exc
            raise
        return from_item(resp["Attributes"])

    def delete(self, owner_id: str, document_id: str) -> None:
        self._db.delete_item(
            TableName=self._table,
            Key={"PK": {"S": pk(owner_id)}, "SK": {"S": sk(document_id)}},
        )
