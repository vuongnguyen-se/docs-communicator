# Phase 2: Infrastructure (queue, DLQ, notification, worker, alarm)

## Context

- `infrastructure/stacks/data.py` owns the documents bucket.
- `api.py` builds the Lambdas through `_function` and tracks them in `self.functions`, which feeds the per-Lambda error alarms in `monitoring.py`.
- `infrastructure/tools/iam_report.py` generates `docs/iam-review.md`.

## Requirements

- **Queues:**
  - `IngestDLQ`: SQS-managed encryption, `enforce_ssl`, 14-day retention, `RemovalPolicy.DESTROY`.
  - `IngestQueue`: SQS-managed encryption, `enforce_ssl`, visibility timeout 6× the worker timeout, and a dead-letter queue (`IngestDLQ`, `max_receive_count=3`).
- **S3 notification:** `OBJECT_CREATED` on the documents bucket to `IngestQueue`, filtered on prefix `uploads/` and suffix `.pdf`.
- **Worker Lambda:**
  - Handler `clouddocs.handlers.ingest_worker.handler`, 30 s timeout, the same runtime and log retention.
  - Same environment variables as the documents Lambda.
  - SQS event source with batch size 5, `report_batch_item_failures=True` and `max_concurrency=2`.
  - Added to `self.functions`, so the `WorkerErrors` alarm is created.
- **Worker IAM (least privilege):**
  - DynamoDB `GetItem` and `UpdateItem` on the table.
  - S3 `GetObject` and `DeleteObject` on `uploads/*.pdf`, `PutObject` on `uploads/*.metadata.json`, and `ListBucket` (for 404 rather than 403).
  - `bedrock:IngestKnowledgeBaseDocuments` (plus what the documents Lambda needed for ingest; mirror its statement) on the Knowledge Base.
  - The SQS consume permissions that the event source adds.
- **New alarm `IngestDLQNotEmpty`:** `ApproximateNumberOfMessagesVisible` ≥ 1 on `IngestDLQ`, routed to the existing SNS topic.

## Files

- Create: `infrastructure/stacks/ingestion.py` (queues, notification, worker).
- Edit:
  - `clouddocs_stack.py`: wiring.
  - `monitoring.py`: the DLQ alarm.
  - `infrastructure/tests/test_stack.py`: new assertions.
- Regenerate: `docs/iam-review.md`.

## Steps

1. Build the `Ingestion` construct and wire it between `Data`/`Knowledge` and `Monitoring`.
2. Tests:
   - both queues encrypted and TLS-only,
   - redrive policy set to 3,
   - notification filter set to `uploads/` + `.pdf`,
   - event source batch 5 with partial failures and max concurrency 2,
   - worker IAM with no `*` resources and actions limited to the list above,
   - the DLQ alarm exists,
   - nothing retained after destroy.
3. Re-run `iam_report.py` and review the new role's statements.

## Validation

Infrastructure `pytest` and `cdk synth` pass locally and in CI.

## Risk / rollback

- **Bucket notification custom resource.** CDK adds a notification-handler Lambda. Its log group is caught by the teardown check's `CloudDocsAI` pattern.
- **Rollback:** remove the construct; the stack update deletes the queues and the notification.
