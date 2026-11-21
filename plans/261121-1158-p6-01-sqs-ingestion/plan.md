# P6-01: S3 event → SQS → ingestion worker, with a DLQ

**Status:** In progress. Approved 2026-11-21; `/complete` is kept as an optional "check now" call (default chosen, see decisions)
**Task:** `TASKS.md` P6-01. "S3 event → SQS → ingestion worker Lambda, with a DLQ (replaces the manual `/complete` call)."

## Outcome

After a browser upload, the document moves `PENDING_UPLOAD → UPLOADED → INDEXING → READY` without the browser calling `/complete`. S3 reports the new object to a queue, and a worker Lambda verifies and ingests it.

## Why

- **Today:** a closed tab or a network drop between the S3 upload and `/complete` leaves the document stuck in `PENDING_UPLOAD` forever.
- **With a queue:** the work survives the browser. Failures are retried, and repeated failures land in a dead-letter queue (DLQ) with an alarm.

## Design

```
Browser --presigned POST--> S3 uploads/<sub>/<doc>.pdf
S3 ObjectCreated (prefix uploads/, suffix .pdf) --> SQS IngestQueue --> Worker Lambda
Worker: key -> (owner, documentId) -> DocumentService.complete_upload(owner, documentId)
3 failed receives --> SQS IngestDLQ --> CloudWatch alarm --> SNS email
```

- **Reuse, don't rewrite.** `complete_upload` already does everything the worker needs:
  - It verifies the size and the `%PDF-` header.
  - It deletes invalid files.
  - It ingests the document.
  - It is idempotent, because status changes are compare-and-set.
- **Trust.** The worker takes the owner and document ID from the key. Only a presigned POST, signed for that exact key, can create it. The worker still requires a matching `PENDING_UPLOAD` record and ignores keys that don't match.
- **Sidecar files.** The suffix filter `.pdf` excludes the `.pdf.metadata.json` files the worker writes itself.
- **Errors:**
  - An unknown key, a missing record, or a record that is no longer `PENDING_UPLOAD` is logged and acknowledged. Retrying cannot fix those.
  - Transient AWS errors are raised, so SQS retries them.
  - Partial batch responses (`ReportBatchItemFailures`) retry only the failed messages.
- **Limits:**
  - Batch size 5 and maximum concurrency 2, so Knowledge Base ingest calls stay gentle.
  - Visibility timeout of 6× the worker timeout.
  - `maxReceiveCount` 3 before a message moves to the DLQ.
- **Cost:** SQS requests are far below the free tier. No idle cost. Everything is destroyed with the stack (D-002).

## Phases

| # | Phase | Files | Status |
|---|---|---|---|
| 1 | [Worker handler](phase-01-worker-handler.md) | backend | Done (114 tests, ruff, mypy) |
| 2 | [Infrastructure: queue, DLQ, notification, worker, alarm](phase-02-infrastructure.md) | infrastructure | Done (37 infra tests; IAM report 10 roles, 0 unreviewed wildcards) |
| 3 | [Frontend: stop calling `/complete`](phase-03-frontend.md) | frontend | Pending |
| 4 | [Docs, live demo, teardown](phase-04-docs-and-demo.md) | docs, AWS 💰🧹 | Pending |

Phases 1 to 3 are code only, with no AWS cost, and CI checks every push. Phase 4 deploys, after the owner's approval.

## Acceptance criteria

1. A PDF uploaded through the UI reaches `READY` with no `/complete` call (verified in the API access pattern and the Lambda logs).
2. A non-PDF renamed `.pdf` ends `FAILED` / `INVALID_FILE`, and its object is deleted.
3. A message the worker cannot process is retried, then moved to the DLQ, the DLQ alarm fires, and the email arrives.
4. Two users' uploads stay isolated (the existing evaluation, 14/14, still passes).
5. CI is green. The IAM report shows the worker's permissions with no unreviewed wildcards.
6. Destroy and the teardown check leave nothing.

## Decisions needed from the owner

- **Keep `POST /documents/{id}/complete`?**
  - **Recommended: keep it as a manual "check now" fallback.** It's idempotent and costs nothing, and it's useful if S3 events are ever delayed.
  - Alternative: remove the route, the handler code and its tests, leaving a single path.
- **DLQ demo:** the demo sends one poison message straight to the queue to prove the retry → DLQ → alarm path. OK?

## Dependencies

PR #5 (P5-08) and PR #7 (CI) merged first, so the worker reuses the current `complete_upload` and every push runs CI.
