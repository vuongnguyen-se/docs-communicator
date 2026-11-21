# API Specification

This contract matches the code in `backend/src/clouddocs/handlers/` and `frontend/src/api/types.ts`. If you change one, change all three.

Base path example: `/api/v1`. All endpoints exchange JSON except the direct S3 upload.

**Authentication:** every route except `GET /health` requires `Authorization: Bearer <Cognito JWT>`. API Gateway's JWT authorizer rejects missing or invalid tokens with `401`. The user ID is taken **only** from the token's `sub` claim.

## Error response

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Only PDF files are supported" }, "requestId": "req-1" }
```

| Status | Codes |
|---|---|
| 400 | `VALIDATION_ERROR` |
| 401 | `UNAUTHORIZED` |
| 404 | `NOT_FOUND` (also returned for other users' documents, so their existence is not revealed) |
| 409 | `CONFLICT`, `LIMIT_EXCEEDED` |
| 429 | Throttled by API Gateway |
| 500 | `INTERNAL_ERROR` (no details) |
| 503 | `UPSTREAM_UNAVAILABLE` |

Never return stack traces, presigned URLs in logs, or internal identifiers such as S3 keys or owner IDs.

## GET /health → 200 (public)
`{ "status": "ok" }`

## POST /documents/upload-url → 201
Request (unknown fields are rejected):
```json
{ "filename": "aws-notes.pdf", "contentType": "application/pdf", "size": 120345 }
```
Response:
```json
{
  "document": { "documentId": "doc_<32 hex>", "filename": "aws-notes.pdf", "fileSize": 120345,
                "status": "PENDING_UPLOAD", "createdAt": "…", "updatedAt": "…", "errorCode": null },
  "upload": { "url": "https://<bucket>.s3.<region>.amazonaws.com/", "fields": { "key": "…", "Content-Type": "application/pdf", "…": "…" } },
  "expiresInSeconds": 300
}
```
The browser POSTs the file as `multipart/form-data` to `upload.url`, sending all `fields` first and `file` last.

This is a **presigned POST**, not a PUT (D-013). Its policy enforces `content-length-range` (≤ 10 MB) and `Content-Type`, which a presigned PUT cannot enforce. The server generates the key `uploads/<sub>/<documentId>.pdf`.

## POST /documents/{id}/complete → 202 (optional)
The browser does **not** need this call. After the S3 upload, S3 notifies the ingestion queue and a worker runs the same steps (D-019). This route is kept as an optional "check now" call:

1. Verifies the stored object: it exists, its real size is within the limit, and it starts with the `%PDF-` header.
2. Calls `IngestKnowledgeBaseDocuments` with `userId` metadata.
3. Sets the status to `INDEXING`.

This call is idempotent. It returns `{ "document": {…} }` with status `INDEXING`, or `FAILED` with `errorCode` `INVALID_FILE` or `INGEST_REQUEST_FAILED`. It returns `409` if the file was not uploaded yet, or if the worker is moving the same document at that moment.

## GET /documents → 200
`{ "documents": [ … ] }`, newest first. Documents in `INDEXING` are refreshed from the Knowledge Base on read. Only a confirmed index sets `READY`.

## GET /documents/{id} → 200
`{ "document": {…} }`

## DELETE /documents/{id}
- `204` once the Knowledge Base confirms removal and the S3 object and record are deleted.
- `202` with `{ "document": {…, "status": "DELETING"} }` while indexed content is still present. Call again later.

## POST /chat/query → 200
Request: `{ "question": "What are the key differences between SQS and SNS?" }` (1–2000 characters).
Planned for Phase 4: an optional `conversationId`, mapped to the Bedrock `sessionId`.
```json
{
  "answer": "…",
  "citations": [ { "documentId": "doc_…", "documentName": "aws-notes.pdf", "excerpt": "…" } ],
  "requestId": "req-1"
}
```
Citations come only from `RetrieveAndGenerate` `retrievedReferences` that map to one of the **caller's own** documents. If none do, `citations` is `[]` and `answer` is a fixed "could not find relevant information" message. Never fabricate citations.

## Limits (configurable through environment variables)
10 MB per file, 5 documents per user, 2000-character questions, upload URL valid for 300 s, request body ≤ 16 KB.
