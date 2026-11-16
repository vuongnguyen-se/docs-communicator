# Phase 2 working plan (backend + pre-flight)

Living tracker for day-to-day alignment. Kept under `backend/` because the working rules
restrict edits to that folder. When you approve, merge the checklist into `docs/tasks.md`
and delete this file, so there is one source of truth.

Legend: `[x]` done, `[ ]` open, `[!]` blocked on a decision, `(AWS)` touches AWS, `($)` can cost money.

## 1. Decisions needed from the owner

| ID | Decision | Recommendation | Status |
|---|---|---|---|
| D1 | Document metadata: (a) S3 data source, no inline metadata for MVP; (b) CUSTOM data source with inline metadata | (a). S3 data sources reject inline metadata, and (b) changes identifiers and citation locations | [x] decided: (a) |
| D2 | Is cross-region inference acceptable? (`architecture.md` §9 Q2) | Decide before choosing the chat model. It can share data across regions | [!] open |
| D3 | AWS profile name for read-only pre-flight, and who creates it | SSO or role with the read-only actions listed in section 4 | [!] open |
| D4 | Monthly budget ceiling | Needed before any billable spike | [!] open |
| D5 | May this plan move to `docs/tasks.md`? Are edits outside `backend/` allowed for docs and Terraform? | Yes for docs now, Terraform later | [!] open |

## 2. Research done (Part A, docs only, 2026-11-15)
- [x] Direct ingestion works on S3 and CUSTOM data sources; S3 sources need S3-location content.
- [x] S3 Vectors is available in ap-southeast-1 and usable as KB vector store.
- [x] `cohere.embed-multilingual-v3` is listed as single-region in ap-southeast-1.
- [x] `RetrieveAndGenerate` response shape matches the parser.
- [x] Found: inline metadata is not allowed for S3 data sources (see B1).
- [x] Found: AWS now recommends "Managed Knowledge Base", which cannot use `RetrieveAndGenerate`. We stay with the standard KB; note this trade-off in the architecture doc.

## 3. Backend tasks (inside `backend/`, no AWS needed)

| ID | Task | Depends on | Status |
|---|---|---|---|
| B1 | Remove inline metadata from `BedrockKnowledgeBase.ingest`; update tests (about 15 lines) | D1 = (a) | [x] |
| B2 | Race: a just-ingested doc may report `NOT_FOUND` and be marked `FAILED`. Grace window (`INDEX_GRACE_SECONDS`, default 300) keeps it `INDEXING`; explicit `FAILED` is not delayed | none, but confirm with spike | [x] |
| B3 | Parser: also handle `customDocumentLocation` and the `metadata` map on references | only if D1 = (b) | [ ] |
| B4 | `ConflictException` on ingest/delete: 3 attempts with 0.5 s/1 s backoff, then 503. Ingest that is busy/throttled leaves the doc `UPLOADED` and `/complete` can be called again | none | [x] |
| B5 | Ownership defence: a citation is kept only if the cited S3 key equals the caller's stored `s3_key` (not just a matching doc id) | none | [x] |
| B6 | Document the env-var contract for Terraform: `DOCUMENTS_BUCKET`, `TABLE_NAME`, `KNOWLEDGE_BASE_ID`, `DATA_SOURCE_ID`, `MODEL_ARN`, plus optional limits | none | [x] |
| B7 | Document the exact IAM actions per Lambda (S3 prefix, DynamoDB table, Bedrock KB and model ARNs) | none | [x] |
| B8 | Lambda packaging: one zip for all handlers, arm64 default, boto3 from the runtime (`scripts/build_lambda.py`) | none | [x] |
| B9 | Log token usage if the API returns it (spec section 9); never log document text | spike | [ ] |
| B10 | Add `moto` or a few integration-style tests only if Stubber tests prove insufficient | none | [ ] |

Done so far: S3, DynamoDB and Bedrock adapters, `build_services`, 30 Stubber tests (87 total passing).

## 4. AWS pre-flight (Part B, read-only, $0) `(AWS)`
Blocked on D2 and D3. Output stored in the scratchpad, summary only in chat, no account ID.

- [ ] P1 `aws sts get-caller-identity` (profile and region sanity, not root)
- [ ] P2 `aws bedrock list-foundation-models --region ap-southeast-1` (embedding and generation models)
- [ ] P3 `aws bedrock list-inference-profiles --region ap-southeast-1`
- [ ] P4 `aws bedrock-agent list-knowledge-bases --region ap-southeast-1` (existing resources)
- [ ] P5 `aws s3vectors list-vector-buckets --region ap-southeast-1` (needs recent CLI)
- [ ] P6 Pricing lookup (Pricing API is us-east-1 only) for Bedrock, S3 Vectors, Cohere embed
- [ ] P7 Findings note: verified vs unverified, tested model IDs, go/no-go

Read-only actions needed: `sts:GetCallerIdentity`, `bedrock:ListFoundationModels`,
`bedrock:GetFoundationModel`, `bedrock:ListInferenceProfiles`, `bedrock:ListKnowledgeBases`,
`bedrock:ListDataSources`, `s3vectors:ListVectorBuckets`, `pricing:GetProducts`.
Model access grant cannot be proven read-only; mark as unverified until a real call.

## 5. Throwaway spike (Part C) `(AWS)($)`, separate approval required
Only if Part A and B leave direct-ingestion behaviour unclear. Needs written approval of
resources, cost estimate and teardown first.

- [x] S1 Proposal drafted: `SPIKE_PROPOSAL.md` (awaiting owner approval; nothing run)
- [ ] S2 Create vector bucket and index (1024 dims, cosine, non-filterable keys `AMAZON_BEDROCK_TEXT` and `AMAZON_BEDROCK_METADATA`)
- [ ] S3 Create KB and S3 data source; run the initial sync
- [ ] S4 Direct-ingest one small PDF; record status sequence and whether `NOT_FOUND` appears early
- [ ] S5 Query once; record citation location type and metadata
- [ ] S6 Delete via API; record how long the index takes to report `NOT_FOUND`
- [ ] S7 Tear everything down and verify nothing is left
- [ ] S8 Feed results into B1, B2, B3 and the architecture doc

## 6. Later (outside `backend/`, needs D5)
- [ ] T1 Terraform: S3 (docs, web), CloudFront and OAC, Cognito without self-signup, HTTP API and JWT authorizer
- [ ] T2 Terraform: Lambdas and least-privilege IAM, DynamoDB, CloudWatch logs and alarms
- [ ] T3 Terraform: S3 Vectors bucket and index, Bedrock KB, S3 data source, service role
- [ ] T4 `terraform plan` reviewed by owner, then approved apply (never run by the agent without an explicit instruction)
- [ ] T5 Manual smoke test and the unrelated-question and Vietnamese tests from `docs/tasks.md`
- [ ] T6 Teardown rehearsal

## 7. Suggested order
1. Owner answers D1 to D5.
2. B1 (and B6, B7, which need no decision).
3. Part B pre-flight, then findings note.
4. B2 and B4, informed by the findings.
5. Decide whether Part C is needed.
6. Terraform (section 6).

## 8. Daily log
Append one entry per working day: what was done, what changed in this file, what is blocked.

### 2026-11-15
- Added S3, DynamoDB, Bedrock adapters, `build_services`, and 30 adapter tests. 87 tests pass.
- Completed Part A research. Found the inline-metadata problem (B1) and the possible `NOT_FOUND` race (B2).
- Created this plan. No AWS calls made, nothing deployed.
- Blocked on D2 to D5 (D1 decided: option a).

### 2026-11-15 (later)
- D1 = (a). Done B1 (inline metadata removed, one test replaces two; 86 tests pass), B6 and B7 (`backend/README.md`).
- Noted: without `s3:ListBucket`, a missing object returns 403 not 404; the README documents this.
- Next: D2/D3 to unblock pre-flight, or B2/B4/B5 which need no decision.

### 2026-11-15 (end of day)
- Done B2, B4, B5. 95 tests pass; ruff and mypy clean. No AWS calls.
- Behaviour change to flag: `POST /documents/{id}/complete` can now return 503 `UPSTREAM_UNAVAILABLE` (index busy or throttled) and leaves the document `UPLOADED`; the client should call it again. The contract sentence for this route was added on request (commit `19aa0e2`), so that item is closed. The mock API and frontend do not retry `/complete` yet (outside `backend/`, needs owner OK).
- Still open: D2 to D5, then Part B pre-flight. Not covered: bucket-name check on cited URIs (ChatService does not know the bucket).

### 2026-11-15 (contract)
- Closed: contract sentence for `/complete` 503 added to `docs/api-contract.md` (`19aa0e2`).
- Open follow-up: frontend/mock API retry of `/complete` on 503 (needs owner OK to edit outside `backend/`).

### 2026-11-16
- Done B8: `backend/scripts/build_lambda.py` builds a reproducible zip (2.5 MiB; arm64 default, x86_64 optional; pydantic as Linux wheels; boto3 from the runtime). Checked: correct `cpython-312-aarch64` binary, identical hash on rebuild, bundled `clouddocs/` byte-identical to `src/`, all modules compile. Not checked: importing from the zip on Linux (host is Windows) or running in a real Lambda.
- Open to verify in the spike: the runtime boto3 version supports `ingest_knowledge_base_documents`.
- Still blocked on D2 to D5 for Part B and Terraform.

### 2026-11-16 (spike proposal)
- Drafted `SPIKE_PROPOSAL.md` (S1): questions Q1-Q9, resources, procedure, cost estimate (expected under $0.50, proposed hard stop $2, partly unverified prices), guardrails, teardown, options A/B/C and an owner approval checklist. Nothing created or run.
- Still blocked on D2-D5 and the read-only profile for Part B.
