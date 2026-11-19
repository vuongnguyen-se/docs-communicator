# Architecture Decision Log

Short records of decisions that shape the project. Add a new entry instead of silently changing an old one. Status values: `Proposed`, `Accepted`, `Verify` (accepted in principle, but must be confirmed against AWS in Phase 0), `Superseded`.

---

## D-001 — AWS Region: `ap-southeast-1` (Singapore)
- **Status:** Accepted
- **Why:** It is closest to the owner, so the UI and API feel faster.
- **Consequence:** Some Bedrock models are only available here through **cross-Region inference profiles** (IDs starting with `apac.`). Requests may be served from another APAC Region. Task P0-05 verifies which models are available.

## D-002 — Ephemeral environments: build → deploy → demo → destroy
- **Status:** Accepted
- **Why:** The free tier has expired. The owner accepts small bills but does not want resources running between sessions.
- **Consequences:**
  - All infrastructure is defined in AWS CDK from Phase 1. Nothing is created by hand except one-time account setup.
  - Every stateful dev resource uses `RemovalPolicy.DESTROY`, and S3 buckets use `autoDeleteObjects`, so `cdk destroy` leaves nothing behind.
  - Every resource is tagged `Project=CloudDocsAI` so leftovers are easy to find.
  - A teardown check script (Phase 1) lists anything still tagged after destroy.
  - Things that stay between sessions: the AWS Budget, the CDK bootstrap stack (small S3 storage cost; it can also be destroyed) and Bedrock model access (no cost).

## D-003 — Infrastructure as Code: AWS CDK (Python) from Phase 1
- **Status:** Accepted
- **Why:** D-002 needs repeatable deploys and complete teardown. This supersedes the old roadmap wording that put CDK in Phase 6.

## D-004 — Authentication: Amazon Cognito before the first public deploy
- **Status:** Accepted
- **Why:** The owner chose the safest option. Without login, anyone who finds the API URL can trigger paid Bedrock calls.
- **Design:**
  - Cognito User Pool with **self sign-up disabled**. Users are created by the admin via CLI or console.
  - API Gateway HTTP API **JWT authorizer** on every route except `GET /health`.
  - Lambdas take `userId` from the verified `sub` claim and never from the request body.
- This moves Cognito from Phase 5 into Phase 1.

## D-005 — RAG engine: Amazon Bedrock Knowledge Bases (managed)
- **Status:** Accepted
- **Why:** This is the documented project scope. One managed service replaces the extract, embed and vector-dump pipeline from the reference diagram (see D-010).

## D-006 — Ingestion: Knowledge Base direct ingestion API
- **Status:** Accepted (proven in spike P0-07, 2026-11-19, `docs/spikes/2026-11-19-knowledge-base-spike.md`)
- **Spike finding:** with an S3 data source, metadata must also come from S3. The backend writes a sidecar `<pdf key>.metadata.json` (`{"metadataAttributes": {"userId", "documentId"}}`) before ingesting, and deletes it with the PDF. Indexing took about 5 s; delete about 5 s.
- **Why:** A normal `StartIngestionJob` syncs the whole data source at once, which conflicts with tracking status per document. `IngestKnowledgeBaseDocuments` handles one document at a time, and `DeleteKnowledgeBaseDocuments` gives a real delete path.
- **Known constraints from AWS docs:**
  - At most 25 documents per API call.
  - Do not run direct ingestion and `StartIngestionJob` at the same time.
  - The data source needs an initial sync after it is created.
  - Deleting from the Knowledge Base does **not** delete the S3 object, so the app must also delete that.
- **Fallback:** Serialized `StartIngestionJob` with a DynamoDB "sync lock" item, so sync jobs never overlap.

## D-007 — Vector store: Amazon S3 Vectors (preferred)
- **Status:** Accepted (proven in spike P0-07: Knowledge Base with `S3_VECTORS` ACTIVE in ap-southeast-1; index float32, 1024 dims, cosine)
- **Why:** Pay-per-use with no idle compute cost, which suits D-002. S3 Vectors itself is available in ap-southeast-1. AWS docs say Knowledge Bases support S3 Vectors "in all regions where both Bedrock and S3 Vectors are available" (prior research, 2026-11-14). P0-06/P0-07 confirm this by actually creating a Knowledge Base.
- **Fallbacks, in order:**
  1. Bedrock-managed vector store option, if offered in the Region.
  2. Aurora PostgreSQL Serverless v2 with pgvector, which can scale to zero.
  3. OpenSearch Serverless. Avoid it: it has an idle cost of roughly hundreds of USD per month.

## D-008 — Models (to be confirmed in P0-05)
- **Status:** Verify
- **Prior research:** The earlier prototype checked AWS docs on 2026-11-14 for `ap-southeast-1`. Re-check it with the CLI in P0-05.
  - **Amazon Titan Text Embeddings V2 is *not* available in Singapore.** Do not plan on it.
  - **Cohere Embed Multilingual v3** (`cohere.embed-multilingual-v3`, 1024 dims, float) is available in the Region. **Chosen**, because the PDFs may be English *and* Vietnamese.
  - Generation is not offered in the Region directly. It goes through cross-Region inference profiles:
    - Amazon Nova Lite through `apac.amazon.nova-lite-v1:0`: cheap, and data stays within APAC.
    - Claude Haiku through a `global.` profile: better quality, especially in Vietnamese, but data may be processed outside APAC.
- **CLI check, 2026-11-18** (`list-foundation-models`, `list-inference-profiles`, `get-foundation-model-availability` in ap-southeast-1):
  - `cohere.embed-multilingual-v3`: on-demand **in-region**, authorized. Titan embeddings are not listed (confirmed).
  - `apac.amazon.nova-lite-v1:0`: inference profile ACTIVE, authorized, agreement available.
  - `global.anthropic.claude-haiku-5-5`: only a `global.` profile, authorized.
  - `anthropic.claude-sonnet-5`: on-demand **in-region**. This is the option if data must stay in Singapore, at a higher price.
  - Cohere and Anthropic show `agreementAvailability: NOT_AVAILABLE`. Expect a Marketplace agreement to be created on first use. A tiny test call confirms it (P0-05).
  - The S3 Vectors API answers in ap-southeast-1 (`list-vector-buckets` returned no buckets).
- **Test calls, 2026-11-18:**
  - Cohere Embed Multilingual v3 ✅ (Vietnamese input, 1024-dim vector).
  - `apac.amazon.nova-lite-v1:0` ✅.
  - `global.anthropic.claude-haiku-5-5` ❌ `AccessDeniedException: ... not available for this account`. Needs the Anthropic first-time-use form in the Bedrock console. This does not block the MVP, because Nova Lite is the default.
- **Spike P0-07 (2026-11-19):** Bedrock's *default* RAG prompt makes Nova Lite emit junk (`Action: GlobalDataSource.search(...)`) and fail on Vietnamese questions. A **custom prompt template** fixed both: clean answers, Vietnamese answers in Vietnamese, refusals when not found. A custom template is therefore **required**. Cross-lingual retrieval (Vietnamese question → English document) works.
- **Plan:** Start with Nova Lite (`apac.`). Switch to Claude Haiku through one config value if Vietnamese answer quality fails the P4-06 evaluation.
- `RetrieveAndGenerate` must receive the **inference profile ARN**, not a bare model ID.
- Model IDs and ARNs live in configuration (CDK context or env vars), never hard-coded in Lambda code.
- **Chunking:** fixed-size (~300 tokens, 10–20% overlap). Avoid hierarchical chunking, because S3 Vectors has a small non-filterable metadata limit.

## D-009 — Frontend hosting: S3 (private) + CloudFront with Origin Access Control
- **Status:** Accepted
- **Why:** This follows `TECH_STACK.md`. The reference diagram uses Amplify Hosting, which also works, but S3 + CloudFront is defined fully in CDK and is torn down with everything else.
- **Libraries:** The frontend uses the Amplify JS library **only** for the Cognito login UI and tokens. This does not use Amplify Hosting.
- **Runtime config:** CDK writes `/config.json` (API URL, Region, user pool and client IDs) at deploy time. One build works for any deployment, and no IDs are committed.
- **CSP `connect-src`** allows `*.execute-api.<region>.amazonaws.com` rather than the exact API host. Naming the exact host would create a CloudFront ↔ API dependency cycle, because the API's CORS needs the CloudFront domain.
- **TLS:** the default `*.cloudfront.net` certificate has a fixed TLS policy. Enforcing TLS 1.2+ would need a custom domain and ACM certificate, which is out of scope for the MVP.

## D-010 — How the reference diagram maps to this project
The owner shared a reference AWS diagram: Amplify, REST API, Cognito, an extract Lambda, SQS, an embed Lambda, vector dumps in S3, Bedrock and DynamoDB. Mapping:

| Reference diagram | CloudDocs AI | When |
|---|---|---|
| Amplify Hosting | S3 + CloudFront (D-009) | Phase 1 |
| Cognito | Cognito User Pool + JWT authorizer (D-004) | Phase 1 |
| API Gateway REST API | API Gateway **HTTP** API (cheaper, simpler, native JWT auth) | Phase 1 |
| CRUD Lambdas + DynamoDB metadata | Document Lambda + DynamoDB | Phase 2 |
| Extract Lambda → SQS → Embed Lambda → vector dump in S3 | Bedrock Knowledge Base (parsing, chunking, embedding, vector store) | Phase 3 |
| Generate-response Lambda → Bedrock | Chat Lambda → `RetrieveAndGenerate` | Phase 4 |
| DynamoDB conversation memory | Bedrock `sessionId`, plus an optional DynamoDB chat table | Phase 4 |
| SQS queue | S3 event → SQS → worker, with DLQ | Phase 6 |

## D-011 — Source control
- **Status:** Accepted
- **Remote:** `github.com/vuongnguyen-se/docs-communicator`. The repository is **public**, so never commit account IDs, ARNs with account IDs, `.env` files or `cdk.context.json` values that contain secrets.
- **Old code:** It was first removed with a normal commit, without force-pushing. After review it was restored (see D-012).

## D-012 — Reuse the earlier prototype code
- **Status:** Accepted (2026-11-17)
- **Why:** The prototype's `backend/` and `frontend/` already implement the documented design: JWT-`sub` identity, server-generated keys, the status state machine, per-document direct ingestion behind a port, the safe delete flow, and citations resolved only against owned documents. Locally, 57 backend tests pass, as do ruff and mypy (strict). The frontend has 6 tests and builds and lints cleanly.
- **What it does not have:** AWS adapters (boto3), CDK infrastructure, Cognito login and the real HTTP client. These are now the Phase 1–4 tasks.
- **Not reused:**
  - `PROJECT_SPEC.md` and the old `docs/`. Their useful findings were moved into D-008 and D-013.
  - Terraform. The project uses CDK (D-003).
- **Code wins where it is stricter:** the API contract and status names now follow the code (`/documents/{id}/complete`, `/chat/query`, status `INDEXING`).

## D-013 — Presigned POST (not PUT) for uploads
- **Status:** Accepted
- **Why:** A presigned POST policy can enforce `content-length-range` (≤ 10 MB) and `Content-Type` at S3 itself. A presigned PUT cannot limit size.
- **Defence in depth:** `/complete` also checks the real object size and the `%PDF-` header.

## D-014 — Bundle a pinned boto3 with the Lambda code
- **Status:** Accepted (2026-11-19)
- **Why:** Per-document ingestion (`IngestKnowledgeBaseDocuments`) is a newer Bedrock API. The boto3 inside the Lambda runtime is chosen by AWS and can lag, so the code would depend on a version we don't control. Bundling `boto3>=1.40,<2` (1.44.6 at the time) makes every deploy behave the same.
- **Cost:** the Lambda package grows to about 42 MB unpacked (limit 250 MB), and cold starts get slightly slower. It is measured in the Phase 3 demo.
- **Revisit:** if cold starts matter, trim botocore's unused service models or use a Lambda layer.

