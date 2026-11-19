# CloudDocs AI Task Board

This is the single place to track progress. Tick a box only when its **Done when** check has really been verified. Decisions referenced as `D-xxx` are in `DECISIONS.md`.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why) · 💰 creates billable AWS resources (ask before running) · 🧹 includes a teardown step

## Progress overview

| Phase | Goal | Status |
|---|---|---|
| 0 | Account, tooling and Region checks; prove the AI path in a throwaway spike | ✅ Done (P0-04 tag activation and optional Claude form left) |
| 1 | Secure skeleton: CDK, Cognito login, HTTP API, health Lambda, hosted frontend | ✅ Done (2026-11-18) |
| 2 | Secure PDF upload with metadata and status | ✅ Done (2026-11-19) |
| 3 | RAG ingestion into Bedrock Knowledge Base | Not started |
| 4 | Grounded chat with citations | Not started |
| 5 | Hardening: delete flow, IAM review, alarms, Guardrails | Not started |
| 6 | Advanced: SQS/DLQ, CI/CD, portfolio polish | Not started |

**Every phase ends the same way:** deploy → run the phase demo → `cdk destroy` → run the teardown check → confirm the bill in Cost Explorer next day.

---

## Phase 0 — Setup and validation

Account and safety (one-time, kept between sessions). Step-by-step guide: `docs/aws-account-setup.md`.
- [x] **P0-01** (2026-11-18: root MFA, no root keys, Identity Center user `vuong-admin` with MFA, single-Region instance in ap-southeast-1) Secure the AWS account: root MFA, no root access keys, and a day-to-day admin identity (IAM Identity Center user preferred, or an IAM user with MFA).
  - Done when: you can sign in as the admin identity, and root has MFA.
- [x] **P0-02** (2026-11-18: SSO profile verified with `get-caller-identity`) Configure the CLI profile `clouddocs-dev`, with Region `ap-southeast-1`.
  - Done when: `aws sts get-caller-identity --profile clouddocs-dev` returns the admin identity.
- [x] **P0-03** (2026-11-18: `clouddocs-monthly` USD 10, alerts at 50%/100% actual and 80% forecast; recipient Active (legacy, already verified)) Create an AWS Budget (e.g. USD 10/month) with email alerts at 50%, 80% and 100% (actual) and 100% (forecasted).
  - Done when: the budget is visible and the alert email is confirmed.
- [ ] **P0-04** Activate the cost allocation tag `Project` in the Billing console.
  - Done when: the tag shows as active. It can take up to 24h to appear after the first tagged resource exists.

Region and model checks (read-only, no cost):
- [~] **P0-05** (2026-11-18: Cohere embed and Nova Lite test calls OK; Claude Haiku needs the Anthropic use-case form, see D-008) List the Bedrock models and inference profiles in `ap-southeast-1`. Choose a generation model and an embedding model, then request model access or submit the Anthropic use-case form (D-008).
  - Commands: `aws bedrock list-foundation-models --region ap-southeast-1`, `aws bedrock list-inference-profiles --region ap-southeast-1`.
  - Done when: both model IDs are recorded in D-008 and access shows **Granted**.
- [x] **P0-06** (2026-11-19: Knowledge Base on S3 Vectors ACTIVE in ap-southeast-1) Confirm which Knowledge Base vector stores are supported in `ap-southeast-1`, S3 Vectors first (D-007).
  - Done when: D-007 is updated to `Accepted` with the chosen store.

Proof of concept (💰 small, 🧹 delete the same day):
- [x] **P0-07** (2026-11-19, done by CLI; report in `docs/spikes/2026-11-19-knowledge-base-spike.md`; all resources deleted) In the console, create a throwaway Knowledge Base with an S3 data source and the chosen vector store. Ingest 1 small PDF with `IngestKnowledgeBaseDocuments`, ask a question with `RetrieveAndGenerate` from the CLI, then delete everything.
  - Done when: an answer with a citation came back, D-006 is updated, observed cost is noted, and all spike resources are deleted.

Tooling and repository:
- [x] **P0-08** (2026-11-18: CLI 2.1148.1; `CDKToolkit` bootstrapped in ap-southeast-1, tagged `Project=CloudDocsAI-Bootstrap` so the teardown check ignores it) Install the AWS CDK CLI (`npm i -g aws-cdk`). Run `cdk bootstrap aws://<account>/ap-southeast-1 --profile clouddocs-dev` 💰 (tiny).
  - Done when: `cdk --version` works and the `CDKToolkit` stack exists.
- [x] **P0-09** Initialize the local git repository and connect it to `github.com/vuongnguyen-se/docs-communicator`. Replace the old code with a normal commit (D-011).
- [x] **P0-10** Record decisions (`DECISIONS.md`) and align the docs with Region, auth and teardown choices.

---

## Phase 1 — Secure skeleton (first deploy)

> **Reused code (D-012):** the backend in `backend/src/clouddocs/` already contains the business logic for upload, complete, status, delete and chat, with in-memory fakes. It has 57 passing tests. The frontend in `frontend/` has upload, list and chat components running against a mock API. What is **missing** is everything that touches AWS: CDK, the boto3 adapters, Cognito login and the real HTTP client.

Repository scaffolding:
- [x] **P1-01** Backend package with tooling (`pyproject.toml`, pytest, ruff, mypy strict) and the frontend scaffold (React 19 + TS + Vite, vitest, eslint). Reused from the earlier prototype.
- [x] **P1-02** Frontend layout shell with documents and chat panels (`App.tsx`, `DocumentList.tsx`, `Chat.tsx`) and a `MockApi` for local development.
- [x] **P1-09** Shared backend HTTP layer (`handlers/common.py`): JSON responses, error shape, request ID logging, identity from JWT `sub` only, body-size limit. Tested.
- [x] **P1-01b** Add `infrastructure/` and `scripts/` folders, plus `frontend/.env.example` (no secrets) and a README section on running tests locally.

Infrastructure (CDK). `[x]` here means synthesized and covered by `infrastructure/tests`. A real deploy is verified in P1-11.
- [x] **P1-03** Create the CDK app skeleton: stack(s) with `Project=CloudDocsAI` tags, dev removal policies (D-002), and config through CDK context (Region, model IDs, allowed origin).
- [x] **P1-04** Create a Cognito User Pool with self sign-up disabled, a strong password policy and an app client without a client secret, configured for the SPA (D-004).
- [x] **P1-05** Create an HTTP API with a JWT authorizer, CORS for the CloudFront origin only, and default route throttling (e.g. 5 rps, burst 10).
- [x] **P1-06** Package the backend as a Lambda asset (Python 3.12 arm64, Docker-free pip bundling of Linux wheels, log retention 1 week). Wire up public `GET /health` and protected `GET /me` (returns the caller's `sub`).
- [x] **P1-07** Create a private S3 site bucket with CloudFront and Origin Access Control (HTTPS redirect, CSP and security headers). Deploy the built frontend plus a deploy-time `/config.json` with `BucketDeployment`.

Frontend auth and client:
- [x] **P1-08** (13 frontend tests; real login verified in P1-11) Replace the mock sign-in with Cognito login through the Amplify JS library (login only). Add `HttpApi` implementing `ApiClient`, which sends the JWT. The app picks Mock or Http from runtime config: `/config.json` when deployed, `VITE_` variables in `npm run dev`.

Operations:
- [x] **P1-10** (2026-11-18: run against AWS; teardown check improved after the first real destroy, see session log) Add `scripts/deploy` and `scripts/destroy`, plus `scripts/check-teardown`, which lists resources still tagged `Project=CloudDocsAI` through the Resource Groups Tagging API.
- [x] **P1-11** 💰🧹 (2026-11-18: deploy in 4.5 min, 9/9 smoke checks, login and "API connected" confirmed by owner, destroyed, teardown check passed) **Phase demo:**
  1. Deploy.
  2. Create a user with the CLI.
  3. Open `WebUrl`, sign in with the temporary password and set a new one. The header shows "API connected (user id …)".
  4. `/health` returns ok.
  5. `GET /me` with the token returns your `sub`; without a token it returns 401.
  6. Destroy.
  7. Run the teardown check, which should come back empty.

---

## Phase 2 — Secure upload

Already done in code (logic + tests, no AWS yet): validation, server-generated keys, the document limit, the status state machine, the `%PDF-` magic check on complete, owner scoping, and idempotent complete.

- [x] **P2-01** CDK (`stacks/data.py`): private document bucket with block public access, SSE-S3 encryption, enforced TLS, CORS for POST from our origins only, and a lifecycle rule to abort incomplete multipart uploads. An age-based expiry of `uploads/` was dropped, because it would also delete real documents; stale `PENDING_UPLOAD` records are moot in ephemeral environments.
- [x] **P2-02** CDK: DynamoDB `Documents` table (on-demand, PK/SK as in `DATABASE_DESIGN.md`, PITR off for dev).
- [x] **P2-03** (10 Stubber tests) Adapter `adapters/dynamodb_repo.py` implementing `DocumentRepository`. `update_status` uses a conditional write; `list` uses a Query, never a Scan. Test it with `botocore` Stubber.
- [x] **P2-04** (6 tests; the policy is decoded and checked) Adapter `adapters/s3_storage.py` implementing `ObjectStorage`: presigned POST with `content-length-range` and `Content-Type` conditions (D-013), `head` with a ranged GET of the first bytes, and `delete`.
- [x] **P2-05** `container.py`: a boto3-backed `Services` factory built from env vars, with `PendingKnowledgeBase` until Phase 3, so documents stay `INDEXING` and are never falsely `READY`. Documents Lambda and 4 routes wired; IAM limited to 5 DynamoDB item actions plus S3 Put/Get/Delete on `uploads/*`, plus `ListBucket` restricted to the `uploads/` prefix (so missing objects return 404, not 403). DELETE route deferred to P5-01.
- [x] **P2-06** Frontend `HttpApi.uploadDocument`: request the URL, then a multipart POST to S3, then `/complete`. Built and unit-tested with P1-08; verified for real in P2-07.
- [x] **P2-07** 💰🧹 (2026-11-19: 19/19 live checks plus the owner's browser upload; destroyed; teardown passed) **Phase demo:**
  - Upload a PDF and see it listed.
  - A non-PDF or a file over 10 MB is rejected.
  - User B gets 404 for user A's document.
  - Destroy.

---

## Phase 3 — RAG ingestion

Already done in code: the `KnowledgeBase` port, poll-on-read status refresh (`INDEXING` → `READY`/`FAILED`) and transient-error handling.

- [ ] **P3-01** CDK: create the vector store chosen in D-007, plus the Knowledge Base (embedding model from D-008, fixed-size chunking), its least-privilege service role and an S3 data source scoped to `uploads/`.
- [ ] **P3-02** CDK: add a custom resource or post-deploy script that runs the required initial data-source sync (D-006).
- [ ] **P3-03** Adapter `adapters/bedrock_kb.py`:
  - `ingest`: write the metadata sidecar `<key>.metadata.json` to S3, then `IngestKnowledgeBaseDocuments` with content and metadata **S3 locations** (inline metadata is rejected for S3 data sources; see spike).
  - `index_state`: `GetKnowledgeBaseDocuments`, mapping statuses to `IndexState`.
  - `delete`: `DeleteKnowledgeBaseDocuments`, plus delete the sidecar together with the PDF.
  - Stubber tests.
- [ ] **P3-04** Frontend: the existing 2 s polling becomes backoff polling (2 s → 10 s), with a clear "indexing…" label.
- [ ] **P3-05** 💰🧹 **Phase demo:** upload 2 small non-sensitive PDFs (one English, one Vietnamese), both reach `READY`, and a CLI `Retrieve` call returns their chunks. Then destroy.

---

## Phase 4 — Grounded chat

Already done in code: question validation, `RetrieveAndGenerate` response parsing (`services/rag.py`), citations resolved only against the caller's own documents, and the fixed "no evidence" answer.

- [ ] **P4-01** `KnowledgeBase.query(question, user_id)`: add a **metadata filter `userId = sub`** so retrieval itself is scoped per user, not just the citations. Update the fakes and tests.
- [ ] **P4-02** Adapter `query`: `RetrieveAndGenerate` with the inference profile ARN (D-008), `maxTokens` cap and the **custom prompt template proven in the spike (required)** (answer only from context, say when unsure, ignore instructions inside documents).
- [ ] **P4-03** Verify `services/rag.py` against a **real** response and fix any field-mapping differences.
- [ ] **P4-04** (Optional) `conversationId` mapped to the Bedrock `sessionId`, plus a DynamoDB chat history table that stores question, answer and citation refs only.
- [~] **P4-05** Frontend `HttpApi.ask` (done with P1-08), then polish the chat UI (message list, expandable citations).
- [ ] **P4-06** Evaluation set: 5 questions with known answers (English and Vietnamese), 3 unrelated questions, 1 prompt-injection PDF and a 2-user isolation test. Record the results in `docs/evaluation.md`.
- [ ] **P4-07** 💰🧹 **Phase demo:** run the end-to-end MVP for all acceptance criteria in `PROJECT_REQUIREMENTS.md` §6, then destroy.

---

## UI design track (frontend only, no AWS cost; can run in parallel using mock mode)

- [ ] **UI-01** Design direction: layout (documents sidebar + chat main area), colours, typography, light and dark mode. Agree on a mockup before coding.
- [ ] **UI-02** Implement the layout and styles (plain CSS, design tokens), plus a styled Cognito login screen that matches.
- [ ] **UI-03** Components: upload drop zone with progress, document cards with status badges, chat bubbles, expandable citations, empty, loading and error states.
- [ ] **UI-04** Accessibility and responsive check (keyboard, contrast, mobile width).
- [ ] **UI-05** Fix misleading error: a missing API route currently shows "Cannot reach the server" (API Gateway's 404 has no CORS headers, so the browser reports a network error). This disappears once Phase 2 routes exist; still show a clearer message.

---

## Phase 5 — Hardening

- [ ] **P5-01** Wire up and verify `DELETE /documents/{id}` (the service logic and tests already exist). It deletes from the Knowledge Base (`DeleteKnowledgeBaseDocuments`), deletes the S3 object, and only then deletes the metadata. Verify the document is no longer retrievable.
- [ ] **P5-02** IAM review: list every Lambda role action and resource, and remove wildcards.
- [ ] **P5-03** CloudWatch alarms for Lambda errors, API 5xx and throttles, with an SNS email topic.
- [ ] **P5-04** Evaluate Bedrock Guardrails (cost and benefit) and record the decision.
- [ ] **P5-05** Retry and error handling review: map boto3 throttling and validation errors to safe responses.
- [ ] **P5-06** Evaluate AWS WAF on CloudFront and the API. Record the decision; it is optional because of its cost.

## Phase 6 — Advanced

- [ ] **P6-01** S3 event → SQS → ingestion worker Lambda, with a DLQ (replaces the manual `/complete` call).
- [ ] **P6-02** Evaluate Step Functions and record the decision.
- [ ] **P6-03** GitHub Actions CI: lint, unit tests, frontend build and `cdk synth` on each PR.
- [ ] **P6-04** (Optional) GitHub Actions deploy through an OIDC role, with no stored AWS keys.
- [ ] **P6-05** Architecture diagram, cost notes from real bills, demo video and screenshots for the portfolio.

---

## Session log

| Date | Work done | AWS resources live after session? | Notes |
|---|---|---|---|
| 2026-11-17 | Planning, decisions, repository set up, prototype code reviewed and reused | None | 57 backend + 6 frontend tests pass locally |
| 2026-11-17 | CDK app: Cognito, HTTP API + JWT authorizer + throttling, health and me Lambdas, scripts | None (synth only) | 10 infra tests, `cdk synth` OK, 59 backend tests |
| 2026-11-17 | S3 + CloudFront (OAC, CSP), runtime `/config.json`, Cognito login (Amplify Authenticator), real `HttpApi` client | None (synth only) | 13 infra + 13 frontend + 59 backend tests |
| 2026-11-18 | Account setup (Identity Center, SSO CLI, budget), old key …IPPF deactivated, Bedrock checks + 3 test calls, `cdk bootstrap`, **first deploy** (Phase 1 demo passed), destroy | None (only `CDKToolkit`, kept on purpose) | Leftovers found after destroy: 2 untagged log groups (deleted). Teardown script now matches any `CloudDocsAI` log group, has `-Cleanup`, and flags stale tagging-index entries. Claude Haiku needs the Anthropic use-case form. |
| 2026-11-19 | HOW_IT_WORKS guide; **Knowledge Base spike P0-07**: S3 Vectors, per-document ingest (~5 s), per-user filter, Vietnamese Q&A, delete, all proven | None (spike resources deleted and verified) | Findings: metadata must be an S3 sidecar file; Bedrock's default prompt fails with Nova Lite, so a custom template is required. |
| 2026-11-19 | **Phase 2** built (adapters, bucket, table, documents API) and demoed: 19/19 live checks (401, validation, S3 policy key/size enforcement, encrypted storage, INDEXING not READY, user isolation 404, fake-PDF cleanup, 409 on missing upload) and a real browser upload | None | Teardown check now filters deleted Cognito pools that the tagging index keeps listing for over a day. Use non-sensitive PDFs from Phase 3 on. |
