"""DynamoDB adapter. Single table: PK=USER#<ownerId>, SK=DOC#<documentId>."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from ..errors import Conflict
from ..models import Document, DocumentStatus
from ..status import ensure_transition
from .errors import aws_error_code, call


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _pk(owner_id: str) -> dict[str, Any]:
    return {"S": f"USER#{owner_id}"}


def _key(owner_id: str, document_id: str) -> dict[str, Any]:
    return {"PK": _pk(owner_id), "SK": {"S": f"DOC#{document_id}"}}


def to_item(doc: Document) -> dict[str, Any]:
    item: dict[str, Any] = {
        **_key(doc.owner_id, doc.document_id),
        "documentId": {"S": doc.document_id},
        "ownerId": {"S": doc.owner_id},
        "filename": {"S": doc.filename},
        "s3Key": {"S": doc.s3_key},
        "fileSize": {"N": str(doc.file_size)},
        "contentType": {"S": doc.content_type},
        "status": {"S": doc.status.value},
        "createdAt": {"S": doc.created_at},
        "updatedAt": {"S": doc.updated_at},
    }
    if doc.ingestion_job_id:
        item["ingestionJobId"] = {"S": doc.ingestion_job_id}
    if doc.error_code:
        item["errorCode"] = {"S": doc.error_code}
    return item


def from_item(item: dict[str, Any]) -> Document:
    return Document(
        document_id=item["documentId"]["S"],
        owner_id=item["ownerId"]["S"],
        filename=item["filename"]["S"],
        s3_key=item["s3Key"]["S"],
        file_size=int(item["fileSize"]["N"]),
        content_type=item["contentType"]["S"],
        status=DocumentStatus(item["status"]["S"]),
        created_at=item["createdAt"]["S"],
        updated_at=item["updatedAt"]["S"],
        ingestion_job_id=item.get("ingestionJobId", {}).get("S"),
        error_code=item.get("errorCode", {}).get("S"),
    )


class DynamoDocumentRepository:
    def __init__(self, client: Any, table: str, now: Callable[[], str] = _now) -> None:
        self._c, self._table, self._now = client, table, now

    def put(self, doc: Document) -> None:
        call(self._c.put_item, TableName=self._table, Item=to_item(doc))

    def get(self, owner_id: str, document_id: str) -> Document | None:
        resp = call(
            self._c.get_item,
            TableName=self._table,
            Key=_key(owner_id, document_id),
            ConsistentRead=True,
        )
        item = resp.get("Item")
        return from_item(item) if item else None

    def list(self, owner_id: str) -> list[Document]:
        docs: list[Document] = []
        start: dict[str, Any] | None = None
        while True:
            args: dict[str, Any] = {
                "TableName": self._table,
                "KeyConditionExpression": "PK = :pk AND begins_with(SK, :p)",
                "ExpressionAttributeValues": {":pk": _pk(owner_id), ":p": {"S": "DOC#"}},
                "ConsistentRead": True,
            }
            if start:
                args["ExclusiveStartKey"] = start
            resp = call(self._c.query, **args)
            docs.extend(from_item(i) for i in resp.get("Items", []))
            start = resp.get("LastEvaluatedKey")
            if not start:
                return sorted(docs, key=lambda d: d.created_at)

    def update_status(
        self,
        owner_id: str,
        document_id: str,
        expected: DocumentStatus,
        new: DocumentStatus,
        error_code: str | None = None,
    ) -> Document:
        ensure_transition(expected, new)
        values: dict[str, Any] = {
            ":expected": {"S": expected.value},
            ":new": {"S": new.value},
            ":now": {"S": self._now()},
        }
        update = "SET #s = :new, updatedAt = :now"
        if error_code:
            update += ", errorCode = :err"
            values[":err"] = {"S": error_code}
        else:
            update += " REMOVE errorCode"
        try:
            resp = call(
                self._c.update_item,
                TableName=self._table,
                Key=_key(owner_id, document_id),
                UpdateExpression=update,
                ConditionExpression="#s = :expected",  # fails if missing or status changed
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if aws_error_code(exc) == "ConditionalCheckFailedException":
                raise Conflict("Document status changed concurrently") from exc
            raise
        return from_item(resp["Attributes"])

    def delete(self, owner_id: str, document_id: str) -> None:
        call(self._c.delete_item, TableName=self._table, Key=_key(owner_id, document_id))
