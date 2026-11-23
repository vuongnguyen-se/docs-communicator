# Technology Stack

What CloudDocs AI uses today, why, and where to find it in the code. Versions are the ones pinned in the repository on 2026-11-23. For the request and data flows, read `docs/HOW_IT_WORKS.md`; for the reasons behind each choice, the `D-xxx` entries in `DECISIONS.md`.

## At a glance

```text
Browser (React SPA)
  │  HTTPS
  ├── CloudFront ── S3 (website files, private)
  ├── Cognito (sign-in, JWT)
  ├── API Gateway HTTP API (JWT check) ── Lambda (Python) ── DynamoDB, S3, Bedrock
  └── S3 (documents, presigned POST) ── SQS ── worker Lambda ── Bedrock Knowledge Base
                                                                  ├── Cohere Embed (vectors)
                                                                  ├── S3 Vectors (vector store)
                                                                  └── Nova Lite (answers)
CloudWatch alarms ── SNS ── email          Everything defined in AWS CDK (Python)
```

## AWS services

| Service | What it does here | Key settings | Code | Decision |
|---|---|---|---|---|
| Region | Everything runs in **ap-southeast-1** (Singapore) | | `infrastructure/cdk.json` | D-001 |
| CloudFront + S3 | Serves the website over HTTPS from a private bucket | Origin Access Control, CSP and security headers, `/config.json` written at deploy | `infrastructure/stacks/web.py` | D-009 |
| Cognito User Pool | Sign-in; issues the JWT the API checks | Self sign-up off (admin creates users), strong password policy, SPA client with no secret | `infrastructure/stacks/auth.py` | D-004 |
| API Gateway (HTTP API) | The REST-style JSON API | JWT authorizer, CORS for the site only, throttling 5 rps / burst 10 | `infrastructure/stacks/api.py` | |
| Lambda | All backend code | Python 3.12, arm64, 256–512 MB, 1-week log retention, pinned boto3 bundled in | `infrastructure/stacks/api.py`, `backend_code.py` | D-014 |
| S3 (documents) | Stores the uploaded PDFs and their metadata sidecar files | Private, SSE-S3 encryption, TLS only, uploads by presigned POST (PDF, ≤ 10 MB) | `infrastructure/stacks/data.py` | D-013 |
| DynamoDB | One record per document (name, size, status) | On demand; Query by user, never Scan | `infrastructure/stacks/data.py` | `DATABASE_DESIGN.md` |
| SQS | Queue between "file uploaded" and "file indexed" | `IngestQueue`: batch 5, concurrency 2; 3 failed tries → `IngestDLQ` (kept 14 days) | `infrastructure/stacks/ingestion.py` | D-019 |
| Bedrock Knowledge Base | Chunks, embeds and searches the documents; runs RetrieveAndGenerate | Fixed-size chunks of 300 tokens with 20% overlap; results filtered by `userId` | `infrastructure/stacks/knowledge.py` | D-005, D-006 |
| Cohere Embed Multilingual v3 | Turns chunks and questions into vectors (English and Vietnamese) | `cohere.embed-multilingual-v3`, 1024 dimensions | `knowledge.py` | D-008 |
| S3 Vectors | Stores the vectors; no cost while idle | float32, cosine distance | `knowledge.py` | D-007 |
| Amazon Nova Lite | Writes the answer from the retrieved passages | `apac.amazon.nova-lite-v1:0` inference profile, temperature 0, at most 400 tokens, top 5 passages, custom prompt | `backend/src/clouddocs/adapters/bedrock_kb.py` | D-008, D-018 |
| CloudWatch + SNS | Alarms that email the owner | Errors per Lambda, API 5xx, 4xx spike, slow chat, DLQ not empty | `infrastructure/stacks/monitoring.py` | |
| Not used, on purpose | Bedrock Guardrails, AWS WAF, Step Functions | Each has triggers for turning it on later | | D-016, D-017, D-020 |

## Application code

| Part | Technology | Versions | Notes |
|---|---|---|---|
| Frontend | React + TypeScript, built with Vite | React 19.3, TypeScript 6.0, Vite 8.3 | Plain CSS with design tokens, light and dark themes, self-hosted Geist fonts (D-015) |
| Sign-in UI | AWS Amplify JS + Amplify UI React | aws-amplify 6.22, @aws-amplify/ui-react 6.15 | Used only for Cognito login; API calls use plain `fetch` |
| Backend | Python Lambda handlers | Python 3.12, boto3 1.40+, pydantic 2 | Handlers → services → adapters (ports and adapters), see below |
| Infrastructure as code | AWS CDK (Python) | aws-cdk-lib 2.277.0 | One app, stacks split by area (D-003) |
| Tests and checks | pytest, ruff, mypy (strict); vitest, eslint | vitest 5.1, eslint 10.15 | Backend tests use in-memory fakes or botocore Stubber, so no AWS is needed |
| CI | GitHub Actions | Python 3.12, Node 22, ubuntu-latest | 3 parallel jobs: backend, frontend, infrastructure (`cdk synth`); no AWS credentials |
| Evaluation | `eval/run_eval.py` with generated fictional PDFs | | 14 cases; results in `docs/evaluation.md` |

## Repository layout

```text
docs-communicator/
├── frontend/src/
│   ├── api/              # ApiClient: http.ts (real API) and a mock for local work
│   ├── components/       # documents panel, upload, chat
│   ├── auth.ts, config.ts, lang.ts, styles.css
├── backend/src/clouddocs/
│   ├── handlers/         # Lambda entry points: health, me, documents, chat, ingest_worker
│   ├── services/         # business logic and the ports (interfaces.py), RAG response parsing
│   ├── adapters/         # boto3 implementations: DynamoDB, S3, Bedrock Knowledge Base
│   ├── container.py      # builds the services from environment variables
│   └── models.py, validators.py, status.py, errors.py, lang.py, config.py
├── backend/tests/
├── infrastructure/
│   ├── app.py, cdk.json
│   ├── stacks/           # auth, web, data, knowledge, ingestion, api, monitoring
│   ├── tools/iam_report.py
│   └── tests/
├── scripts/              # deploy, destroy, check-teardown, create-user (PowerShell)
├── eval/                 # evaluation script and PDF generator
├── docs/                 # guides, evaluation, IAM review, portfolio
└── .github/workflows/ci.yml
```

## Configuration

Nothing secret lives in the repository. CDK passes resource names to each Lambda as environment variables (`DOCUMENTS_BUCKET`, `DOCUMENTS_TABLE`, `KNOWLEDGE_BASE_ID`, `DATA_SOURCE_ID`, `MODEL_ARN`), and limits such as `MAX_FILE_BYTES` and `MAX_DOCUMENTS` have defaults in `backend/src/clouddocs/config.py`. The browser reads the Cognito IDs and the API URL from `/config.json`, written at deploy time; in `npm run dev` they come from `VITE_` variables (see `frontend/.env.example`). Lambda functions use their execution roles, never access keys.

Never put access keys, secret keys, session tokens or passwords in `.env` files, frontend variables, source code or Git.
