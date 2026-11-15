# API Contract (as implemented in Phase 1)

All routes except `/health` require a Cognito JWT (`Authorization: Bearer <token>`). The user identity is taken from the JWT `sub` claim only. Errors always look like:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Only PDF files are supported" }, "requestId": "req-1" }
```

| Status | Codes |
|---|---|
| 400 | `VALIDATION_ERROR` |
| 401 | `UNAUTHORIZED` |
| 404 | `NOT_FOUND` (also returned for other users' documents) |
| 409 | `CONFLICT`, `LIMIT_EXCEEDED` |
| 500 | `INTERNAL_ERROR` (no details) |
| 503 | `UPSTREAM_UNAVAILABLE` |

## POST /documents/upload-url → 201
Request (unknown fields rejected):
```json
{ "filename": "aws-notes.pdf", "contentType": "application/pdf", "size": 120345 }
```
Response:
```json
{
  "document": { "documentId": "doc_<32 hex>", "filename": "aws-notes.pdf", "fileSize": 120345,
                "status": "PENDING_UPLOAD", "createdAt": "…", "updatedAt": "…", "errorCode": null },
  "upload": { "url": "https://<bucket>.s3.<region>.amazonaws.com/", "fields": { "key": "…", "Content-Type": "application/pdf" } },
  "expiresInSeconds": 300
}
```
The browser then POSTs the file as `multipart/form-data` to `upload.url` with all `fields` first and `file` last.
(Phase 2 note: the S3 adapter must add policy conditions for `content-length-range` ≤ 10 MB.)

## POST /documents/{id}/complete → 202
Verifies the stored object (exists, real size, `%PDF-` header), then starts indexing. Idempotent. Returns `{ "document": {…, "status": "INDEXING"} }`, or `status: "FAILED"` with `errorCode` `INVALID_FILE` / `INGEST_REQUEST_FAILED`. `409` if the file was not uploaded yet. `503` `UPSTREAM_UNAVAILABLE` if the knowledge base is busy or throttled (including an overlapping sync that persists after bounded retries): the document stays `UPLOADED` and the client should call this endpoint again; the call is safe to repeat.

## GET /documents → 200
`{ "documents": [ … ] }`. Documents in `INDEXING` are refreshed from the knowledge base; only a confirmed index sets `READY`.

## GET /documents/{id} → 200
`{ "document": {…} }`

## DELETE /documents/{id}
- `204` once the index confirms removal and the S3 object and record are deleted.
- `202` with `{ "document": {…, "status": "DELETING"} }` while indexed content is still present; call again later.

## POST /chat/query → 200
Request: `{ "question": "What are the key differences between SQS and SNS?" }` (1–2000 chars)
```json
{
  "answer": "…",
  "citations": [ { "documentId": "doc_…", "documentName": "aws-notes.pdf", "excerpt": "…" } ],
  "requestId": "req-1"
}
```
If no retrieved passage maps to one of the caller's documents, `citations` is `[]` and `answer` is a fixed "could not find relevant information" message.

## GET /health → 200
`{ "status": "ok" }`

## Limits (configurable)
10 MB per file, 5 documents, 2000-character questions, presigned URL valid 300 s, request body ≤ 16 KB.
