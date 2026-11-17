# Development Roadmap

This file explains the **why and order** of the phases. The detailed, tickable checklist lives in `TASKS.md`. Decisions are in `DECISIONS.md`.

## Working rules

- Complete and verify one phase before starting the next.
- Environments are **ephemeral** (D-002). Each phase ends with deploy → demo → `cdk destroy` → teardown check.
- All AWS resources are created with CDK (D-003). The only exceptions are one-time account setup and the Phase 0 spike, which is deleted the same day.
- Ask before any step marked 💰 in `TASKS.md`.

## Phase 0: Validate design (before coding)
Secure the account, set a budget, and configure the CLI for `ap-southeast-1`. Confirm the Bedrock model, Knowledge Base and vector-store support in that Region. Run a short console spike that proves the full AI path: ingest one PDF and get one cited answer. Then delete it.
**Deliverable:** decisions D-006, D-007 and D-008 are confirmed, and the expected cost is known.

## Phase 1: Secure skeleton
CDK app, Cognito (no self sign-up), HTTP API with JWT authorizer and throttling, health Lambda, React app on S3 + CloudFront with login. Deploy and teardown scripts.
**Deliverable:** a logged-in user calls a protected endpoint, unauthenticated calls get 401, and teardown leaves nothing behind.

## Phase 2: Secure document upload
Private document bucket, DynamoDB table, presigned upload URL endpoint, validation, and a document list scoped to the user.
**Deliverable:** a PDF is stored privately and listed with its status, only for its owner.

## Phase 3: RAG ingestion
Knowledge Base, vector store and S3 data source in CDK. Per-document direct ingestion with `userId` metadata and status tracking.
**Deliverable:** uploaded content becomes retrievable, and the document is marked `READY` only after that is confirmed.

## Phase 4: AI chat
`RetrieveAndGenerate` filtered to the user's own documents, citation mapping, a no-source state, conversation sessions and an evaluation set.
**Deliverable:** end-to-end grounded question answering. All MVP acceptance criteria pass.

## Phase 5: Hardening
Full delete flow, IAM least-privilege review, alarms, retry and error handling, and Guardrails and WAF evaluations.
**Deliverable:** a robust, reviewable MVP.

## Phase 6: Advanced architecture
SQS + DLQ ingestion worker, a Step Functions evaluation, GitHub Actions CI (and optional OIDC deploy), and portfolio material.
**Deliverable:** a reproducible, observable portfolio deployment.
