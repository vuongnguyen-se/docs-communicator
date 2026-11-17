# API Specification

Base path example: `/api/v1`. All endpoints exchange JSON except the direct S3 upload.

**Authentication:** every endpoint except `GET /health` requires `Authorization: Bearer <Cognito JWT>`. Missing or invalid tokens are rejected by API Gateway with `401`. The user ID is taken from the token's `sub` claim.

## 0. Health

`GET /health` (public) returns `200 {"status": "ok"}`.

## 1. Create upload URL

`POST /documents/upload-url`

Request:

```json
{
  "fileName": "aws-notes.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 123456
}
```

Response `200`:

```json
{
  "documentId": "generated-id",
  "uploadUrl": "short-lived-presigned-url",
  "method": "PUT",
  "requiredHeaders": {
    "Content-Type": "application/pdf"
  },
  "expiresInSeconds": 300
}
```

The upload URL is a temporary bearer credential. Do not log it or persist it in chat history.

## 2. Complete upload / request ingestion

`POST /documents/{documentId}/ingest`

Request:

```json
{
  "etag": "optional-s3-etag"
}
```

Response `202`:

```json
{
  "documentId": "generated-id",
  "status": "PROCESSING",
  "message": "Ingestion has been requested."
}
```

The implementation must verify the object exists at the expected S3 key before starting ingestion. The exact ingestion orchestration must account for Knowledge Base data-source sync semantics and avoid overlapping jobs.

## 3. List documents

`GET /documents`

Response `200`:

```json
{
  "items": [
    {
      "documentId": "generated-id",
      "fileName": "aws-notes.pdf",
      "status": "READY",
      "createdAt": "2026-01-01T10:00:00Z"
    }
  ]
}
```

## 4. Get document

`GET /documents/{documentId}`

Response `200`:

```json
{
  "documentId": "generated-id",
  "fileName": "aws-notes.pdf",
  "status": "READY",
  "createdAt": "2026-01-01T10:00:00Z",
  "updatedAt": "2026-01-01T10:05:00Z"
}
```

## 5. Ask a question

`POST /chat`

Request:

```json
{
  "question": "Explain the difference between SQS and SNS.",
  "conversationId": "optional-conversation-id"
}
```

Response `200`:

```json
{
  "answer": "Generated answer grounded in retrieved document content.",
  "conversationId": "conversation-id",
  "citations": [
    {
      "text": "Retrieved source excerpt, if returned and appropriate to display.",
      "sourceUri": "S3 source URI or mapped source reference, if returned",
      "metadata": {}
    }
  ]
}
```

This is an application-level contract. Map the actual Bedrock response carefully; citation fields and metadata must come from the service response. Do not fabricate a citation when none is returned.

## 6. Delete document (later milestone)

`DELETE /documents/{documentId}`

Before implementing, define how the source object, metadata, and indexed Knowledge Base content are removed or excluded. Do not return success if only the DynamoDB metadata was deleted while the document remains retrievable.

## Error response

Use a consistent shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "A concise explanation safe to show to the user.",
    "requestId": "correlation-id"
  }
}
```

Use suitable HTTP status codes: `400`, `401`, `403`, `404`, `409`, `413`, `429`, and `500` as appropriate. Never return stack traces or internal credentials to the browser.
