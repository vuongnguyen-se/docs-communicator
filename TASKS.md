# CloudDocs AI Task Board

This is the single place to track progress. Tick a box only when its **Done when** check has really been verified. Decisions referenced as `D-xxx` are in `DECISIONS.md`.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why) · 💰 creates billable AWS resources (ask before running) · 🧹 includes a teardown step

## Progress overview

| Phase | Goal | Status |
|---|---|---|
| 0 | Account, tooling and Region checks; prove the AI path in a throwaway spike | In progress |
| 1 | Secure skeleton: CDK, Cognito login, HTTP API, health Lambda, hosted frontend | Not started |
| 2 | Secure PDF upload with metadata and status | Not started |
| 3 | RAG ingestion into Bedrock Knowledge Base | Not started |
| 4 | Grounded chat with citations | Not started |
| 5 | Hardening: delete flow, IAM review, alarms, Guardrails | Not started |
| 6 | Advanced: SQS/DLQ, CI/CD, portfolio polish | Not started |

**Every phase ends the same way:** deploy → run the phase demo → `cdk destroy` → run the teardown check → confirm the bill in Cost Explorer next day.

---

## Phase 0 — Setup and validation

Account and safety (one-time, kept between sessions):
- [ ] **P0-01** Secure the AWS account: root MFA, no root access keys, and a day-to-day admin identity (IAM Identity Center user preferred, or an IAM user with MFA).
  - Done when: you can sign in as the admin identity, and root has MFA.
- [ ] **P0-02** Configure the CLI profile `clouddocs-dev`, with Region `ap-southeast-1`.
  - Done when: `aws sts get-caller-identity --profile clouddocs-dev` returns the admin identity.
- [ ] **P0-03** Create an AWS Budget (e.g. USD 10/month) with email alerts at 50%, 80% and 100% (actual) and 100% (forecasted).
  - Done when: the budget is visible and the alert email is confirmed.
- [ ] **P0-04** Activate the cost allocation tag `Project` in the Billing console.
  - Done when: the tag shows as active. It can take up to 24h to appear after the first tagged resource exists.

Region and model checks (read-only, no cost):
- [ ] **P0-05** List the Bedrock models and inference profiles in `ap-southeast-1`. Choose a generation model and an embedding model, then request model access or submit the Anthropic use-case form (D-008).
  - Commands: `aws bedrock list-foundation-models --region ap-southeast-1`, `aws bedrock list-inference-profiles --region ap-southeast-1`.
  - Done when: both model IDs are recorded in D-008 and access shows **Granted**.
- [ ] **P0-06** Confirm which Knowledge Base vector stores are supported in `ap-southeast-1`, S3 Vectors first (D-007).
  - Done when: D-007 is updated to `Accepted` with the chosen store.

Proof of concept (💰 small, 🧹 delete the same day):
- [ ] **P0-07** In the console, create a throwaway Knowledge Base with an S3 data source and the chosen vector store. Ingest 1 small PDF with `IngestKnowledgeBaseDocuments`, ask a question with `RetrieveAndGenerate` from the CLI, then delete everything.
  - Done when: an answer with a citation came back, D-006 is updated, observed cost is noted, and all spike resources are deleted.

Tooling and repository:
- [ ] **P0-08** Install the AWS CDK CLI (`npm i -g aws-cdk`). Run `cdk bootstrap aws://<account>/ap-southeast-1 --profile clouddocs-dev` 💰 (tiny).
  - Done when: `cdk --version` works and the `CDKToolkit` stack exists.
- [x] **P0-09** Initialize the local git repository and connect it to `github.com/vuongnguyen-se/docs-communicator`. Replace the old code with a normal commit (D-011).
- [x] **P0-10** Record decisions (`DECISIONS.md`) and align the docs with Region, auth and teardown choices.

---

## Phase 1 — Secure skeleton (first deploy)

Repository scaffolding:
- [ ] **P1-01** Create the folder structure (`frontend/`, `backend/`, `infrastructure/`, `scripts/`), `.env.example`, and Python tooling (venv, `ruff`, `pytest`).
- [ ] **P1-02** Scaffold the React + TypeScript + Vite frontend with a layout shell: header, documents panel, chat panel.

Infrastructure (CDK):
- [ ] **P1-03** Create the CDK app skeleton: stack(s) with `Project=CloudDocsAI` tags, dev removal policies (D-002), and config through CDK context (Region, model IDs, allowed origin).
- [ ] **P1-04** Create a Cognito User Pool with self sign-up disabled, a strong password policy and an app client without a client secret, configured for the SPA (D-004).
- [ ] **P1-05** Create an HTTP API with a JWT authorizer, CORS for the CloudFront origin only, and default route throttling (e.g. 5 rps, burst 10).
- [ ] **P1-06** Create a health Lambda (Python 3.12, small memory, log retention 1 week) behind public `GET /health`, plus one protected `GET /me` that returns the caller's `sub`.
- [ ] **P1-07** Create a private S3 site bucket with CloudFront and Origin Access Control. Deploy the built frontend with `BucketDeployment`.

Frontend auth:
- [ ] **P1-08** Add Cognito login to the frontend with the Amplify JS library (login only). Send the ID or access token in the `Authorization` header.

Backend foundations:
- [ ] **P1-09** Create a shared backend module: JSON response helpers, the error shape from `API_SPECIFICATION.md`, structured logging with request ID, and unit tests.

Operations:
- [ ] **P1-10** Add `scripts/deploy` and `scripts/destroy`, plus `scripts/check-teardown`, which lists resources still tagged `Project=CloudDocsAI` through the Resource Groups Tagging API.
- [ ] **P1-11** 💰🧹 **Phase demo:**
  1. Deploy.
  2. Create a user with the CLI.
  3. Log in and see `/me` respond.
  4. Confirm an unauthenticated call to `/me` returns 401.
  5. Destroy.
  6. Run the teardown check, which should come back empty.

---

## Phase 2 — Secure upload

- [ ] **P2-01** Create a private document bucket: block public access, SSE-S3 encryption, enforce TLS, CORS for PUT from the site origin, and a lifecycle rule that deletes abandoned `uploads/` objects.
- [ ] **P2-02** Create the DynamoDB `Documents` table (on-demand, PK/SK as in `DATABASE_DESIGN.md`, PITR off for dev).
- [ ] **P2-03** Add `POST /documents/upload-url`:
  - Validate name, type (`application/pdf`) and size limit.
  - The backend generates the key `uploads/<sub>/<documentId>/<safeName>`.
  - Use a presigned PUT that expires in 300 s.
  - Create a record with status `PENDING_UPLOAD`.
- [ ] **P2-04** Add `GET /documents` and `GET /documents/{id}`, always scoped to the caller's `sub`.
- [ ] **P2-05** Frontend: file picker, size and type checks, direct PUT to S3, then a refreshed list with status badges.
- [ ] **P2-06** Unit tests for validation, key generation and status transitions.
- [ ] **P2-07** 💰🧹 **Phase demo:**
  - Upload a PDF and see it listed.
  - Uploads that are not PDFs or are too large are rejected with a 4xx.
  - User A cannot read user B's document.
  - Destroy.

---

## Phase 3 — RAG ingestion

- [ ] **P3-01** CDK: create the vector store chosen in D-007, plus the Knowledge Base, its service role (least privilege) and an S3 data source scoped to the `uploads/` prefix.
- [ ] **P3-02** CDK: add a custom resource or post-deploy script that runs the required initial data-source sync (D-006).
- [ ] **P3-03** Add `POST /documents/{id}/ingest`:
  - Verify that the object exists and that its key is owned by the caller.
  - Call `IngestKnowledgeBaseDocuments` with `userId` metadata.
  - Set status to `PROCESSING`.
- [ ] **P3-04** Status tracking: `GET /documents/{id}` checks `GetKnowledgeBaseDocuments` while the document is `PROCESSING`, then moves it to `READY` or `FAILED`. Transitions must be idempotent.
- [ ] **P3-05** Frontend: show "processing…" and poll with backoff until `READY` or `FAILED`.
- [ ] **P3-06** Tests: map Bedrock document statuses to app statuses (with mocked boto3 / `botocore.stub`).
- [ ] **P3-07** 💰🧹 **Phase demo:** upload 2 small non-sensitive PDFs, both reach `READY`, and a CLI `Retrieve` call returns their chunks. Then destroy.

---

## Phase 4 — Grounded chat

- [ ] **P4-01** Add `POST /chat`:
  - Validate the question (length limit).
  - Call `RetrieveAndGenerate` with a **metadata filter `userId = sub`**.
  - Map `conversationId` to the Bedrock `sessionId`.
- [ ] **P4-02** Map citations using only fields the service actually returned (S3 URI to file name through DynamoDB). Return an explicit "no source found" state.
- [ ] **P4-03** Prompt template: answer only from the retrieved context, say when unsure, and ignore instructions found inside documents.
- [ ] **P4-04** (Optional) DynamoDB chat history table, storing question, answer and citation refs only.
- [ ] **P4-05** Frontend chat UI: message list, loading, error and empty states, and expandable citations.
- [ ] **P4-06** Evaluation set: 5 questions with known answers, 3 unrelated questions and 1 prompt-injection PDF. Record the results in `docs/evaluation.md`.
- [ ] **P4-07** 💰🧹 **Phase demo:** run the end-to-end MVP for all acceptance criteria in `PROJECT_REQUIREMENTS.md` §6, then destroy.

---

## Phase 5 — Hardening

- [ ] **P5-01** Add `DELETE /documents/{id}`. It deletes from the Knowledge Base (`DeleteKnowledgeBaseDocuments`), deletes the S3 object, and only then deletes the metadata. Verify the document is no longer retrievable.
- [ ] **P5-02** IAM review: list every Lambda role action and resource, and remove wildcards.
- [ ] **P5-03** CloudWatch alarms for Lambda errors, API 5xx and throttles, with an SNS email topic.
- [ ] **P5-04** Evaluate Bedrock Guardrails (cost and benefit) and record the decision.
- [ ] **P5-05** Retry and error handling review: map boto3 throttling and validation errors to safe responses.
- [ ] **P5-06** Evaluate AWS WAF on CloudFront and the API. Record the decision; it is optional because of its cost.

## Phase 6 — Advanced

- [ ] **P6-01** S3 event → SQS → ingestion worker Lambda, with a DLQ (replaces the manual `/ingest` call).
- [ ] **P6-02** Evaluate Step Functions and record the decision.
- [ ] **P6-03** GitHub Actions CI: lint, unit tests, frontend build and `cdk synth` on each PR.
- [ ] **P6-04** (Optional) GitHub Actions deploy through an OIDC role, with no stored AWS keys.
- [ ] **P6-05** Architecture diagram, cost notes from real bills, demo video and screenshots for the portfolio.

---

## Session log

| Date | Work done | AWS resources live after session? | Notes |
|---|---|---|---|
| 2026-11-17 | Planning, decisions, repository set up | None | — |
