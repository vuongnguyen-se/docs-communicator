# Database Design

## DynamoDB: Documents table

Suggested table name: `CloudDocsDocuments`

### Key schema

- Partition key: `PK` (String)
- Sort key: `SK` (String)

### Document item

```json
{
  "PK": "USER#<userId>",
  "SK": "DOC#<documentId>",
  "documentId": "doc_<32 hex>",
  "userId": "<userId-or-local-demo-user>",
  "filename": "aws-notes.pdf",
  "s3Key": "uploads/<userId>/<documentId>.pdf",
  "contentType": "application/pdf",
  "fileSize": 123456,
  "status": "UPLOADED",
  "ingestionJobId": null,
  "errorCode": null,
  "createdAt": "2026-01-01T10:00:00Z",
  "updatedAt": "2026-01-01T10:00:00Z"
}
```

The values above are illustrative, not real records.

### Status values

- `PENDING_UPLOAD`
- `UPLOADED`
- `INDEXING`
- `READY`
- `FAILED`
- `DELETING`

Allowed transitions (enforced in `backend/src/clouddocs/status.py`):
`PENDING_UPLOAD → UPLOADED → INDEXING → READY | FAILED`, and any state `→ DELETING → (record removed)`.
Status updates are conditional writes (compare-and-set on the expected current status).

## Optional chat history table

Suggested table name: `CloudDocsChat`

- Partition key: `PK` = `USER#<userId>`
- Sort key: `SK` = `CHAT#<conversationId>#MESSAGE#<timestamp>#<messageId>`

Store only the information needed for the product. Avoid storing sensitive document contents or full prompts unless there is a clear requirement.

## Access patterns

1. List documents for a user, newest first.
2. Get one document by user ID and document ID.
3. Update a document's processing status.
4. (Optional) list messages in a conversation.

## Important

- Do not scan the entire table for normal user requests.
- Always scope reads and writes to the authenticated user: `userId` is the Cognito `sub` claim.
- `ingestionJobId` holds the direct-ingestion document identifier (or the sync job ID under the D-006 fallback).
- Add GSIs only when a real access pattern requires them.
