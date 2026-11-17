# Technology Stack

## Proposed defaults

| Area | Choice | Notes |
|---|---|---|
| Frontend | React + TypeScript + Vite | SPA |
| UI | Plain CSS or a lightweight component library | Avoid unnecessary complexity |
| Frontend hosting | S3 + CloudFront | HTTPS delivery |
| Region | ap-southeast-1 | D-001 |
| Auth | Amazon Cognito User Pool + HTTP API JWT authorizer | Amplify JS used only for login UI (D-004, D-009) |
| API | API Gateway HTTP API | REST-style JSON endpoints |
| Backend | Python 3.12 Lambda | Confirm runtime availability in target Region |
| AWS SDK | boto3 | Use Lambda execution role credentials |
| Metadata | DynamoDB | On-demand capacity for small portfolio workload |
| Files | S3 | Private bucket, lifecycle policy if appropriate |
| RAG | Amazon Bedrock Knowledge Bases | Managed ingestion and retrieval |
| Generation | Bedrock foundation model | Select based on Region, access, quality, and cost |
| Embeddings | Bedrock embedding model | Must match Knowledge Base configuration |
| Logs | CloudWatch Logs | Structured logging |
| Vector store | Amazon S3 Vectors (preferred) | Verify in Region (D-007) |
| IaC | AWS CDK with Python | From Phase 1 (D-003) |

## Repository layout

```text
clouddocs-ai/
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
├── backend/
│   ├── document_api/
│   ├── chat_api/
│   ├── shared/
│   ├── tests/
│   └── requirements.txt
├── infrastructure/
│   ├── app.py
│   ├── stacks/
│   └── requirements.txt
├── scripts/          # deploy / destroy / teardown check
├── docs/
├── .env.example
├── .gitignore
└── README.md
```

Adjust this layout if the chosen deployment framework requires a different structure, but explain the reason first.

## Configuration

Use environment variables or deployment outputs for non-secret configuration, such as:
- `AWS_REGION`
- `DOCUMENTS_BUCKET`
- `DOCUMENTS_TABLE`
- `CHAT_HISTORY_TABLE` (if implemented)
- `KNOWLEDGE_BASE_ID`
- `BEDROCK_MODEL_ARN` or the model identifier required by the selected API
- `ALLOWED_ORIGIN`
- `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID` (frontend; public identifiers, not secrets)

Never put access keys, secret keys, session tokens, or passwords in `.env.example`, frontend variables, source code, or Git.
