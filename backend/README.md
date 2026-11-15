# CloudDocs AI backend

Python 3.12 Lambda handlers + service layer. AWS access goes through ports
(`services/interfaces.py`) with boto3 adapters in `adapters/` and in-memory fakes in `tests/`.

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest && ruff check . && ruff format --check . && mypy src
```

No AWS credentials are needed for tests (adapter tests use botocore `Stubber`).

## Lambda entry points

| Handler | Routes | Notes |
|---|---|---|
| `clouddocs.handlers.documents.handler` | `POST /documents/upload-url`, `POST /documents/{id}/complete`, `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}` | Needs S3, DynamoDB, KB admin actions |
| `clouddocs.handlers.chat.handler` | `POST /chat/query` | Needs DynamoDB read and KB query |
| `clouddocs.handlers.health.handler` | `GET /health` | Touches no AWS service; logs only |

Package `src/clouddocs` as the Lambda root. boto3 is provided by the Lambda runtime and is
not bundled (decision on pinning is open: PLAN.md B8).

## Environment variables (B6): the contract Terraform must satisfy

Required by `documents` and `chat` (`container.build_services()` reads all five on first use,
so the chat function needs the bucket and data source values even though it never writes):

| Variable | Example | Used for |
|---|---|---|
| `DOCUMENTS_BUCKET` | `clouddocs-docs-dev-<suffix>` | Private bucket holding `uploads/<userId>/<docId>.pdf` |
| `TABLE_NAME` | `clouddocs-documents-dev` | DynamoDB table (PK `USER#<id>`, SK `DOC#<id>`) |
| `KNOWLEDGE_BASE_ID` | `KB12345678` | Bedrock knowledge base |
| `DATA_SOURCE_ID` | `DS12345678` | The **S3-type** data source of that KB (decision D1a) |
| `MODEL_ARN` | model or inference-profile ARN | Generation model for `RetrieveAndGenerate` |

Optional (defaults in `config.py`):

| Variable | Default |
|---|---|
| `MAX_FILE_BYTES` | `10485760` |
| `MAX_DOCUMENTS` | `5` |
| `MAX_QUESTION_CHARS` | `2000` |
| `UPLOAD_URL_TTL_SECONDS` | `300` |
| `INDEX_GRACE_SECONDS` | `300` (how long a just-submitted document may be missing from the index before it is marked FAILED) |

Provided by Lambda itself: `AWS_REGION`. Nothing here is a secret; no credentials or keys
are ever configured as environment variables.

Non-code infrastructure requirements implied by the backend:
- The documents bucket needs a **CORS rule** allowing `POST` from the CloudFront origin
  (the browser uploads with a presigned POST).
- Bucket Block Public Access on; lifecycle rule for abandoned objects and incomplete uploads.
- Lambda timeout longer than the Bedrock call (chat: start at 30 s; documents: 15 s).
- API Gateway body limit: handlers reject bodies over 16 KB.

## IAM per Lambda (B7)

Principle: one role per function, resource ARNs scoped, no `*` except where AWS requires it.
Status: derived from the code and AWS docs; **not yet exercised against a live account**.
Items marked (verify) must be confirmed in the Phase 2 spike.

### `documents` function

| Service | Actions | Resource | Why |
|---|---|---|---|
| S3 | `s3:PutObject` | `arn:aws:s3:::<bucket>/uploads/*` | Needed so the presigned POST signed by this role is accepted |
| S3 | `s3:GetObject` | `arn:aws:s3:::<bucket>/uploads/*` | `head_object` and the 8-byte ranged read for the `%PDF-` check |
| S3 | `s3:ListBucket` | `arn:aws:s3:::<bucket>` with condition `s3:prefix` = `uploads/*` | Without it a missing object returns 403 instead of 404, which the adapter would not treat as "not uploaded" |
| S3 | `s3:DeleteObject` | `arn:aws:s3:::<bucket>/uploads/*` | Delete flow and rejected uploads |
| DynamoDB | `PutItem`, `GetItem`, `Query`, `UpdateItem`, `DeleteItem` | table ARN | Repository (no index, so no index ARN) |
| Bedrock | `bedrock:IngestKnowledgeBaseDocuments`, `bedrock:GetKnowledgeBaseDocuments`, `bedrock:DeleteKnowledgeBaseDocuments` | `arn:aws:bedrock:<region>:<account>:knowledge-base/<KB_ID>` | Direct ingestion, status, delete |
| Logs | `logs:CreateLogStream`, `logs:PutLogEvents` | its own log group ARN | Structured logs |

Not granted: any model invocation, `StartIngestionJob`, or access to other prefixes.
The initial data-source sync is done once by the owner, not by this function.

### `chat` function

| Service | Actions | Resource | Why |
|---|---|---|---|
| DynamoDB | `GetItem` | table ARN | Maps each cited document id back to the caller's own document |
| Bedrock | `bedrock:RetrieveAndGenerate`, `bedrock:Retrieve` | KB ARN (verify whether `RetrieveAndGenerate` supports resource scoping) | Query |
| Bedrock | `bedrock:InvokeModel` | the model in `MODEL_ARN`; if it is an inference profile, also the profile ARN and the underlying foundation-model ARNs in each profile region (verify) | Generation step |
| Logs | as above | own log group | |

Not granted: S3, DynamoDB writes, KB document actions.

### `health` function
Logs permissions only.

### Other principals (for the Terraform tasks, not Lambda)
- **Bedrock KB service role**: read `s3:GetObject` and `s3:ListBucket` on the documents bucket,
  `bedrock:InvokeModel` on the embedding model, and S3 Vectors access to the one index
  (`s3vectors:*` actions per the AWS "Create a service role for Knowledge Bases" page; verify
  the exact list).
- **Owner (one-time)**: `bedrock:StartIngestionJob` for the initial sync.

## Known open points
Tracked in `PLAN.md`: packaging (B8) and the remaining spike items. The adapter's Bedrock request shapes are validated against the botocore
model but not against the live service.
