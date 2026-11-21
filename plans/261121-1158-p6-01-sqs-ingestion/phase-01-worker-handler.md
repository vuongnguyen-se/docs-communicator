# Phase 1: Worker handler

## Context

`DocumentService.complete_upload(user_id, document_id)` (`backend/src/clouddocs/services/documents.py`) verifies, cleans up and ingests. It is idempotent. `validators.document_id_from_key` already parses `uploads/<sub>/<doc>.pdf`.

## Requirements

- New handler `backend/src/clouddocs/handlers/ingest_worker.py`, for SQS events containing S3 notifications.
- For each SQS record:
  - Parse the S3 event (it may hold several `Records`), URL-decode each key (`unquote_plus`), and keep keys under `uploads/` ending in `.pdf`.
  - Derive the owner and document ID from the key with `validators`; an invalid key is logged and skipped.
  - Call `complete_upload`. `NotFound`, `Conflict` ("Upload not found") and already-processed documents are logged and acknowledged.
  - Any other exception counts as a failure for that record, so SQS retries it.
  - Also skip S3 `s3:TestEvent` messages, which S3 sends once when notifications are configured.
- Return `{"batchItemFailures": [{"itemIdentifier": messageId}, ...]}`.
- Log the `documentId` and outcome. Never log file contents.
- Wiring: the same `get_services()` container, with no new ports.

## Files

- Create: `backend/src/clouddocs/handlers/ingest_worker.py`, `backend/tests/test_ingest_worker.py`
- Possibly edit: `backend/src/clouddocs/validators.py` (an owner-from-key helper next to `document_id_from_key`)

## Steps

1. Add an `owner_and_document_from_key(key)` helper with a regex shared with `_KEY_RE`.
2. Write the handler with per-record try/except and partial batch failures.
3. Tests, using the existing fakes:
   - a valid upload reaches `INDEXING`,
   - a fake PDF ends `FAILED` / `INVALID_FILE`,
   - an unknown key and a sidecar key are skipped,
   - a `TestEvent` is skipped,
   - a repeated message stays a no-op,
   - a repository error makes only that message a batch item failure,
   - one S3 event with 2 records is handled.

## Validation

`pytest`, `ruff` and `mypy --strict` pass locally and in CI.

## Risk / rollback

Low. A new file, and existing paths are untouched. Rollback: delete the handler.
