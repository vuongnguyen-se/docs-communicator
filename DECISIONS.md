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
- **Status:** Verify (P0-07 spike)
- **Why:** A normal `StartIngestionJob` syncs the whole data source at once, which conflicts with tracking status per document. `IngestKnowledgeBaseDocuments` handles one document at a time, and `DeleteKnowledgeBaseDocuments` gives a real delete path.
- **Known constraints from AWS docs:**
  - At most 25 documents per API call.
  - Do not run direct ingestion and `StartIngestionJob` at the same time.
  - The data source needs an initial sync after it is created.
  - Deleting from the Knowledge Base does **not** delete the S3 object, so the app must also delete that.
- **Fallback:** Serialized `StartIngestionJob` with a DynamoDB "sync lock" item, so sync jobs never overlap.

## D-007 — Vector store: Amazon S3 Vectors (preferred)
- **Status:** Verify (P0-06)
- **Why:** Pay-per-use with no idle compute cost, which suits D-002. S3 Vectors itself is available in ap-southeast-1. Whether **Bedrock Knowledge Bases can use S3 Vectors in ap-southeast-1** still needs confirming.
- **Fallbacks, in order:**
  1. Bedrock-managed vector store option, if offered in the Region.
  2. Aurora PostgreSQL Serverless v2 with pgvector, which can scale to zero.
  3. OpenSearch Serverless. Avoid it: it has an idle cost of roughly hundreds of USD per month.

## D-008 — Models (to be confirmed in P0-05)
- **Status:** Verify
- **Generation:** A cost-efficient Anthropic Claude model on Bedrock, Haiku-class first, through an `apac.` inference profile if needed.
- **Embeddings:** Amazon Titan Text Embeddings V2, or a Cohere Embed model if Titan is unavailable in the Region.
- Model IDs and ARNs live in configuration (CDK context or env vars), never hard-coded in Lambda code.

## D-009 — Frontend hosting: S3 (private) + CloudFront with Origin Access Control
- **Status:** Accepted
- **Why:** This follows `TECH_STACK.md`. The reference diagram uses Amplify Hosting, which also works, but S3 + CloudFront is defined fully in CDK and is torn down with everything else.
- **Libraries:** The frontend uses the Amplify JS library **only** for the Cognito login UI and tokens. This does not use Amplify Hosting.

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
- **Old code:** It was replaced by a normal commit, without force-pushing, so it is still recoverable from git history.
