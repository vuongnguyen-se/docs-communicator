# CloudDocs AI Task Board

This is the single place to track progress. Tick a box only when its **Done when** check has really been verified. Decisions referenced as `D-xxx` are in `DECISIONS.md`.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why) · 💰 creates billable AWS resources (ask before running) · 🧹 includes a teardown step

## Progress overview

| Phase | Goal | Status |
|---|---|---|
| 0 | Account, tooling and Region checks; prove the AI path in a throwaway spike | ✅ Done (only the optional Claude form, P0-05, is left) |
| 1 | Secure skeleton: CDK, Cognito login, HTTP API, health Lambda, hosted frontend | ✅ Done (2026-11-18) |
| 2 | Secure PDF upload with metadata and status | ✅ Done (2026-11-19) |
| 3 | RAG ingestion into Bedrock Knowledge Base | ✅ Done (2026-11-19) |
| 4 | Grounded chat with citations | ✅ Done (2026-11-20): **MVP complete** |
| 5 | Hardening: delete flow, IAM review, alarms, Guardrails | ✅ Done (2026-11-21): demo passed, P5-08 name mix-up fixed |
| 6 | Advanced: SQS/DLQ, CI/CD, portfolio polish | In progress: P6-03 CI, P6-01 SQS/DLQ and P6-02 decision done (2026-11-21) |

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
- [x] **P0-04** (2026-11-21: `Project` (type Resource) Active, confirmed with `aws ce list-cost-allocation-tags`; the IAM-principal `Project` tag stays inactive, not needed) Activate the cost allocation tag `Project` in the Billing console.
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

- [x] **P3-01** (`stacks/knowledge.py`; 6 stack tests) CDK: create the vector store chosen in D-007, plus the Knowledge Base (embedding model from D-008, fixed-size chunking), its least-privilege service role and an S3 data source scoped to `uploads/`.
- [x] **P3-02** CDK: a custom resource (`AwsCustomResource`, `StartIngestionJob` on create) runs the required first data-source sync at deploy (D-006).
- [x] **P3-03** (16 Stubber tests; `query` refuses until Phase 4 adds the user filter) Adapter `adapters/bedrock_kb.py`:
  - `ingest`: write the metadata sidecar `<key>.metadata.json` to S3, then `IngestKnowledgeBaseDocuments` with content and metadata **S3 locations** (inline metadata is rejected for S3 data sources; see spike).
  - `index_state`: `GetKnowledgeBaseDocuments`, mapping statuses to `IndexState`.
  - `delete`: `DeleteKnowledgeBaseDocuments`, plus delete the sidecar together with the PDF.
  - Stubber tests.
- [x] **P3-04** Frontend: backoff polling 2 s → 3 s → 4.5 s … capped at 10 s, with readable status labels ("Indexing…", "Ready"); 3 tests.
- [x] **P3-05** 💰🧹 (2026-11-19: after an IAM fix, 10/10 live checks; the owner's 2 PDFs, EN + VI, reached Ready; passages labelled with the owner's userId; another user retrieves 0; destroyed; teardown passed) **Phase demo:** upload 2 small non-sensitive PDFs (one English, one Vietnamese), both reach `READY`, and a CLI `Retrieve` call returns their chunks. Then destroy.

---

## Phase 4 — Grounded chat

Already done in code: question validation, `RetrieveAndGenerate` response parsing (`services/rag.py`), citations resolved only against the caller's own documents, and the fixed "no evidence" answer.

- [x] **P4-01** (the port now *requires* `owner_id`; adapter refuses an empty one; test proves every chat query carries the caller) `KnowledgeBase.query(question, user_id)`: add a **metadata filter `userId = sub`** so retrieval itself is scoped per user, not just the citations. Update the fakes and tests.
- [x] **P4-02** (Stubber test pins the exact request: filter, profile ARN, template, `temperature: 0`) Adapter `query`: `RetrieveAndGenerate` with the inference profile ARN (D-008), `maxTokens` cap and the **custom prompt template proven in the spike (required)** (answer only from context, say when unsure, ignore instructions inside documents).
- [x] **P4-03** `services/rag.py` matches the response shape seen live in spike P0-07 (`citations[].retrievedReferences[].content.text` / `.location.s3Location.uri`); re-confirmed in the P4-07 demo.
- [ ] **P4-04** (Optional) `conversationId` mapped to the Bedrock `sessionId`, plus a DynamoDB chat history table that stores question, answer and citation refs only.
- [x] **P4-05** Frontend `HttpApi.ask` plus chat UI: conversation list, expandable sources per answer, explicit "no source" state. Visual design follows in the UI track.
- [x] **P4-06** (2026-11-20: **11/11 passed**, about 1 s per answer; report `docs/evaluation.md`; re-run with `eval/run_eval.py`) Evaluation set: 5 questions with known answers (English and Vietnamese), 3 unrelated questions, 1 prompt-injection PDF and a 2-user isolation test. Record the results in `docs/evaluation.md`.
- [x] **P4-07** 💰🧹 (2026-11-20: all 12 acceptance criteria met, see `docs/acceptance.md`; destroyed; teardown passed first run) **Phase demo:** run the end-to-end MVP for all acceptance criteria in `PROJECT_REQUIREMENTS.md` §6, then destroy.

---

## UI design track (frontend only, no AWS cost; can run in parallel using mock mode)

- [x] **UI-01** (2026-11-20: canvas mockup approved after the owner's brand was applied; D-015) Design direction: layout (documents sidebar + chat main area), colours, typography, light and dark mode. Agree on a mockup before coding.
- [x] **UI-02** (self-hosted Geist fonts, dark/light tokens, layout, styled sign-in; the Cognito screen's styling is verified on the next deploy) Implement the layout and styles (plain CSS, design tokens), plus a styled Cognito login screen that matches.
- [x] **UI-03** (multi-file drag-and-drop, per-file progress via XHR, per-file rejection, document cards, chat bubbles, source chips) Components: upload drop zone with **multi-file selection** (owner request, 2026-11-19) and per-file progress, document cards with status badges, chat bubbles, expandable citations, empty, loading and error states.
- [x] **UI-04** (headless check: every control named, 0 small buttons, no sideways scroll, alt text, skip link, focus rings, reduced motion; phone layout with collapsible documents and a pinned question box) Accessibility and responsive check (keyboard, contrast, mobile width).
- [x] **UI-05** (clearer network/404/401/upload messages; Delete hidden until P5-01 wires it) Fix misleading error: a missing API route currently shows "Cannot reach the server" (API Gateway's 404 has no CORS headers, so the browser reports a network error). This disappears once Phase 2 routes exist; still show a clearer message.

- [x] **UI-06** (the decline answer and the 'no source' note follow the question's language (backend clouddocs/lang.py + frontend lang.ts)) The no-evidence answer is a fixed English sentence; answer in the question's language (Vietnamese questions currently get English).

---

## Phase 5 — Hardening

- [x] **P5-01** (2026-11-21, P5-07: after delete, 0 items in DynamoDB, S3 and the Knowledge Base, 0 retrieval results; the document stopped answering within 4 s of the `202`) Wire up and verify `DELETE /documents/{id}` (the service logic and tests already exist). It deletes from the Knowledge Base (`DeleteKnowledgeBaseDocuments`), deletes the S3 object, and only then deletes the metadata. Verify the document is no longer retrievable.
- [x] **P5-02** (`infrastructure/tools/iam_report.py` -> `docs/iam-review.md`: 8 roles, 16 statements, 0 unreviewed wildcards) IAM review: list every Lambda role action and resource, and remove wildcards.
- [~] **P5-03** (alarms per Lambda, API 5xx, 4xx spike, chat p90 latency -> SNS; email at deploy time only (`-AlarmEmail`); 2026-11-21, P5-07: a forced 4xx spike fired `Api4xxSpike` within 2 min, the email arrived, and the alarm returned to OK on its own) CloudWatch alarms for Lambda errors, API 5xx and throttles, with an SNS email topic.
- [x] **P5-04** (D-016: not enabled for the MVP, with triggers to enable it) Evaluate Bedrock Guardrails (cost and benefit) and record the decision.
- [x] **P5-05** (AWS throttling/unavailable -> 503 SERVICE_BUSY with a safe message; other AWS errors generic 500) Retry and error handling review: map boto3 throttling and validation errors to safe responses.
- [x] **P5-06** (D-017: not enabled for the MVP, with triggers to enable it) Evaluate AWS WAF on CloudFront and the API. Record the decision; it is optional because of its cost.
- [x] **P5-07** 💰🧹 (2026-11-21: steps 1–7 passed; step 6 used a simulated user-B request to the Documents Lambda, as `eval/run_eval.py` does; destroyed; teardown passed after a fix to `check-teardown.ps1`, see session log) **Phase demo:** live checks for P5-01 and P5-03, plus the items left for "the next deploy". Use 1 small, non-sensitive PDF and 2 users (A and B). Done when every step passes, the results are recorded in the session log, and P5-01, P5-03 and Phase 5 are ticked.
  1. **Deploy** with `scripts\deploy.ps1 -AlarmEmail <your email>`. This is also the first real run of `scripts\use-infra-venv.ps1`. Open the "AWS Notification – Subscription Confirmation" email and click **Confirm subscription**.
  2. **Sign-in screen (UI-02):** the Cognito sign-in card shows the Clouddocs styling and stays readable in both light and dark mode.
  3. **Alarms exist (P5-03):** CloudWatch → Alarms lists 7 alarms whose names contain `HealthErrors`, `MeErrors`, `DocumentsErrors`, `ChatErrors`, `Api5xx`, `Api4xxSpike` and `ChatSlow` (CDK adds the stack prefix). Each is in `OK` or "Insufficient data", never `ALARM`.
  4. **Alarm email arrives (P5-03):** send 60 requests to `GET /me` without a token, about 4 per second (each one gets a 401). Within about 10 minutes, `Api4xxSpike` goes to `ALARM` and the alarm email arrives. It then returns to `OK` on its own.
  5. **Delete removes everything (P5-01):** as user A, upload the PDF, wait for **Ready**, then ask a question it answers *with a source*. Delete the document from the UI and accept the confirmation. Then check:
     - The document disappears from the list. A `202` (still `DELETING`) is fine if it is gone after the next refresh.
     - The same question now gets the "could not find relevant information" answer, with no sources.
     - S3: neither `uploads/<A's sub>/<documentId>.pdf` nor its `.pdf.metadata.json` sidecar exists.
     - DynamoDB: the item `USER#<A's sub>` / `DOC#<documentId>` is gone.
     - Knowledge Base: `aws bedrock-agent get-knowledge-base-documents` for that document returns nothing, or a not-found status.
  6. **Delete is owner-only:** user A uploads a PDF. User B sends `DELETE /documents/<A's documentId>` with B's token. The answer is `404`, and A's document is still listed and still answerable.
  7. **Destroy and check:** run `scripts\destroy.ps1`. The teardown check passes, with no stacks, tagged resources, log groups or SNS topic left. Confirm the bill in Cost Explorer the next day.
- [x] **P5-08** (2026-11-21: prompt rule plus a `NO_ANSWER` decline marker, D-018; evaluation 14/14 with 3 new `ABS-*` cases; the demo question was declined in English and Vietnamese with no sources) Name mix-up in answers (found in the P5-07 demo, 2026-11-21). The only document (`non-sensitive-pdf-docs.pdf`) described a UX designer named Huỳnh Trị. Asked "could you tell me a bit about Hung Vuong?", the answer described Huỳnh Trị's profile (VietMind, V-bits) as "Hùng Vương" and cited the PDF, so a wrong answer looked sourced. Retrieval and deletion were correct; the model assumed the person asked about was the person in the passages.
  - Fix: add a rule to `PROMPT_TEMPLATE` (`backend/src/clouddocs/adapters/bedrock_kb.py`): answer about a named person, company or thing only if the search results name it; otherwise say it is not in the documents, in the question's language.
  - Evaluation: add cases to `eval/run_eval.py` (English and Vietnamese) that ask about a name absent from the fictional PDFs, expecting a decline with no sources; re-run and record in `docs/evaluation.md`.
  - Done when: the new cases pass, the existing 11 still pass, and a live check repeats the demo question with a decline.

## Phase 6 — Advanced

- [x] **P6-01** (2026-11-21, D-019: worker reuses `complete_upload`; `/complete` kept as an optional "check now"; live demo: 3 PDFs READY via the queue in 7.9 s, fake PDF `FAILED` and deleted, broken message → 3 retries → DLQ → alarm email; evaluation 14/14) S3 event → SQS → ingestion worker Lambda, with a DLQ (replaces the manual `/complete` call).
- [x] **P6-02** (2026-11-21, D-020: not used for the MVP; the worker's job is one step, SQS gives retries and a DLQ, and polling on read finishes indexing and deletes; triggers and a first design are recorded) Evaluate Step Functions and record the decision.
- [x] **P6-03** (2026-11-21: `.github/workflows/ci.yml`, 3 parallel jobs, no AWS credentials; first run green on PR #7: backend 21 s, frontend 16 s, infrastructure with real `cdk synth` 66 s) GitHub Actions CI: lint, unit tests, frontend build and `cdk synth` on each PR.
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
| 2026-11-19 | Progress deck; **Phase 3** built and demoed: Knowledge Base on S3 Vectors in CDK, automatic first sync, Bedrock adapter with sidecar metadata | None (destroyed, teardown passed) | Found in the demo: per-document ingestion needs `bedrock:StartIngestionJob` (the spike ran as admin, so it could not catch this); fixed and redeployed in 32 s. READY in about 4 s. Cold start about 6 s with the bundled boto3 (D-014), warm 78 ms. Teardown cleanup now retries because helper log groups can reappear. |
| 2026-11-20 | **Phase 4 / MVP demo**: chat endpoint deployed; evaluation 11/11; owner browser test (an English question about a Vietnamese PDF was answered with its source; questions about another user's documents were declined); all 12 acceptance criteria met | None (destroyed, teardown passed) | Found in the demo: RetrieveAndGenerate with an inference profile needs `bedrock:GetInferenceProfile`; fixed in 32 s. Added README configuration, evaluation and cleanup sections. |
| 2026-11-20 | **UI track**: taste-skill (dealt palette/type, chat-chip pattern) → canvas mockup → owner's brand applied (logo, mark, blue/navy/amber) → built in the app; Vietnamese decline (UI-06) | None (local mock mode only) | Headless Edge driver: 8 screenshots, 0 console errors; found and fixed 2 phone bugs (panel wouldn't collapse, top bar wrapped). |
| 2026-11-20 | **Phase 5 (code)**: delete flow wired (P5-01), AWS error mapping to 503 `SERVICE_BUSY` (P5-05), faster cold starts, CloudWatch alarms + SNS (P5-03), IAM report `docs/iam-review.md` (P5-02), Guardrails and WAF decisions D-016/D-017 | None (no deploy) | P5-01 and P5-03 still need a live check in the Phase 5 demo. |
| 2026-11-21 | Synced a second worktree with `main`; installed Python 3.12.10 there (winget, user scope) | None | On `main` at 817de92: 104 backend tests (ruff, mypy strict), 31 infra tests, 25 frontend tests, lint and build all pass. |
| 2026-11-21 | **Phase 5 demo (P5-07)** from the second machine (new `clouddocs-dev` SSO profile, CDK CLI 2.1149.0): deploy 5 min, 7 alarms OK, forced 4xx spike fired `Api4xxSpike` and the email arrived, delete verified in DynamoDB, S3, Knowledge Base and retrieval (no answers 4 s after the `202`), other-user delete 404, owner checked the sign-in screen. Scripts: `deploy.ps1 -RequireApproval`, `destroy.ps1 -Force` for non-interactive runs | None (destroyed; teardown passed; only `CDKToolkit`) | Found: (1) P5-08 name mix-up in an answer; (2) `check-teardown.ps1` crashed under `destroy.ps1` (inherited `ErrorActionPreference=Stop` turned an expected Cognito not-found into an error, so `-Cleanup` was skipped); fixed and re-run: 2 log groups deleted, check passed. A chat answer that stayed on screen after its PDF was deleted was an old message, not a new answer (chat call times confirm). |
| 2026-11-21 | **P5-08 live check**: prompt rule alone fixed the name mix-up, but the first evaluation run was 10/14: Bedrock attached citations to correct declines (ABS-1..3, and UN-1 regressed; ABS-2 declined in English). Added the `NO_ANSWER` decline marker (D-018), redeployed (22 s), re-ran: **14/14**; demo question declined in English and Vietnamese with no sources | None (destroyed; teardown passed in `destroy.ps1` itself, 3 log groups cleaned) | Evaluation PDFs generated outside the repo; `eval/venv` is git-ignored. |
| 2026-11-21 | **P6-01 queued ingestion** built (worker Lambda, `IngestQueue` + `IngestDLQ`, S3 → SQS notification, `IngestDLQNotEmpty` alarm; the browser and the eval script stop calling `/complete`) and demoed: deploy 11 min, 9 alarms OK; broken message retried 3× → DLQ → alarm → email (after the subscription was confirmed); fake PDF `FAILED` / `INVALID_FILE` and deleted in 13 s; 3 PDFs READY via the queue in 7.9 s; evaluation 14/14 | None (destroyed; teardown passed; only `CDKToolkit`) | The tagging index briefly kept listing the deleted SQS event-source mapping; `list-event-source-mappings` and `list-queues` confirmed 0. An alarm fired before the email subscription is confirmed sends no email: confirm first, or reset the alarm state to re-send. |
