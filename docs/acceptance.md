# MVP acceptance review (2026-11-20)

Criteria from `PROJECT_REQUIREMENTS.md` §6, checked against live deployments (each destroyed afterwards).

| # | Criterion | Evidence | Result |
|---|---|---|---|
| 1 | Frontend requests an upload URL and uploads a PDF to private S3 | Owner's browser uploads in Phases 2–4; a direct S3 read of the bucket returned 403 | ✅ |
| 2 | Backend records document metadata in DynamoDB | Items checked in the Phase 2 and 3 demos | ✅ |
| 3 | The Knowledge Base ingests the document | Owner's PDFs reached Ready; 3 evaluation PDFs Ready in 6 s | ✅ |
| 4 | UI shows whether ingestion is complete | "Indexing…" → "Ready" with backoff polling | ✅ |
| 5 | Questions answered through `RetrieveAndGenerate` | Evaluation 11/11 (`docs/evaluation.md`); owner's browser test | ✅ |
| 6 | Sources included when Bedrock returns them | Expandable sources with the exact passage; declined answers show none | ✅ |
| 7 | Invalid requests return useful 4xx errors | 400 validation, 401 without token, 404 for another user's document, 409 for a missing upload | ✅ |
| 8 | Logs available in CloudWatch | Both demo fixes (Phase 3 and 4) were diagnosed from the Lambda logs | ✅ |
| 9 | README explains deployment, configuration, testing, cleanup | README sections: run tests, deploy and tear down, configuration, evaluation, cost and cleanup | ✅ |
| 10 | No AWS credentials or secrets committed | Repository scan: 0 account IDs, 0 AWS key IDs, 0 secret values, 0 env/output files | ✅ |
| 11 | Unauthenticated calls rejected; no cross-user access | 401 checks; evaluation ISO-1; owner's questions about the test user's documents were declined | ✅ |
| 12 | `cdk destroy` + teardown check leave nothing | Teardown check passed; 0 Knowledge Bases, vector buckets, buckets and tables remained | ✅ |

**Known limitations (tracked in `TASKS.md`):** no visual design yet (UI track); the decline message is always English (UI-06); delete is not wired (P5-01); about 6 s cold start after a deploy (D-014).
