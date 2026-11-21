"""Ingestion worker: SQS messages carrying S3 "object created" events for uploads.

S3 reports every new uploads/<sub>/<documentId>.pdf to the ingest queue. For each one this
worker runs DocumentService.complete_upload, the same repeat-safe code as
POST /documents/{id}/complete: it checks the real size and the %PDF- header, deletes an
invalid file, and starts indexing. So the browser no longer has to call /complete.

Error policy:
- Nothing to do (a key that is not an upload, a missing record, a file already handled):
  log and acknowledge. Retrying cannot change the outcome.
- Anything else (AWS errors, an unreadable message): report that message as a batch item
  failure, so SQS retries it. After 3 receives it moves to the dead-letter queue, whose
  alarm emails the owner.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import unquote_plus

from ..container import get_services
from ..errors import Conflict, NotFound
from ..validators import owner_and_document_from_key

log = logging.getLogger("clouddocs.worker")


def _upload_keys(message_body: str) -> list[str]:
    """Object keys in one S3 event notification (it can hold several records)."""
    event = json.loads(message_body)
    if event.get("Event") == "s3:TestEvent":  # sent once when the notification is set up
        return []
    return [
        unquote_plus(record["s3"]["object"]["key"])  # S3 URL-encodes keys in events
        for record in event.get("Records", [])
        if record.get("eventSource") == "aws:s3"
    ]


def _process(key: str) -> None:
    parsed = owner_and_document_from_key(key)
    if parsed is None:
        log.warning(json.dumps({"outcome": "skipped", "reason": "not an upload key"}))
        return
    owner, document_id = parsed
    try:
        doc = get_services().documents.complete_upload(owner, document_id)
    except (NotFound, Conflict) as exc:
        log.info(json.dumps({"documentId": document_id, "outcome": "skipped", "reason": exc.code}))
        return
    log.info(json.dumps({"documentId": document_id, "outcome": doc.status.value}))


def handler(event: dict[str, Any], context: Any) -> dict[str, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        try:
            for key in _upload_keys(record["body"]):
                _process(key)
        except Exception:
            log.exception(json.dumps({"messageId": record.get("messageId"), "outcome": "retry"}))
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
