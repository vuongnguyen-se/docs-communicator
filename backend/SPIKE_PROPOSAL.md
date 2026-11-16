# Part C: Knowledge Base spike proposal (DRAFT, nothing approved, nothing run)

Status: **draft for owner review**. No AWS resource will be created until the owner approves
this document in writing (see section 10). Prepared 2026-11-16. Region under test: `ap-southeast-1`.

## 1. Purpose
Answer, with one real document, the questions that documentation cannot settle, so the Terraform
work (T1 to T3) is built on facts instead of assumptions.

| # | Question | Code or doc it feeds |
|---|---|---|
| Q1 | Does `IngestKnowledgeBaseDocuments` accept an S3-location PDF on an S3 data source, exactly as `BedrockKnowledgeBase.ingest` sends it? | adapter `ingest` |
| Q2 | What status sequence does `GetKnowledgeBaseDocuments` report (STARTING, IN_PROGRESS, INDEXED ...)? | `_STATE_MAP` |
| Q3 | Right after ingest, does the index briefly report `NOT_FOUND`, and for how long? | B2 grace window (default 300 s) |
| Q4 | Does `RetrieveAndGenerate` return `s3Location.uri` for citations, with the bucket and key we expect? | parser, B5 ownership check |
| Q5 | After `DeleteKnowledgeBaseDocuments`, how long until the status is `NOT_FOUND`? Does the passage stop appearing in answers? | delete flow, definition of done |
| Q6 | Does an unrelated question return no citations (so we show "no relevant information")? | chat service |
| Q7 | What do the token-usage fields look like (if any)? | B9 |
| Q8 | Which exact IAM actions were needed (from AccessDenied messages with a tight role)? | README IAM "(verify)" items |
| Q9 | Does the chosen generation model work in `ap-southeast-1` directly, or only via an inference profile? | D2, `MODEL_ARN` |

Also answerable without AWS (docs lookup, free): which boto3 version the Lambda Python 3.12 runtime ships.

## 2. Preconditions (all must be true before any create call)
- [ ] D2 answered (cross-region inference yes or no).
- [ ] D3 done: a profile exists. Part B (read-only checks) completed with a **go**.
- [ ] D4: owner states a budget ceiling for the spike.
- [ ] Owner approves this proposal (section 10), including the write-capable profile in section 6.
- [ ] Teardown script written, reviewed and dry-run (section 8) **before** the first create.
- [ ] Model access for the embedding and generation models confirmed in the account (this may
      need a one-time console step by the owner; I cannot do it).

## 3. Resources to create (all prefixed `clouddocs-spike-`, tagged `project=clouddocs-spike`)
| # | Resource | Setting | Always-on cost? |
|---|---|---|---|
| 1 | S3 bucket (documents) | Block Public Access, SSE-S3, one test PDF | No (cents or less) |
| 2 | S3 Vectors bucket | default SSE-S3 | Storage only |
| 3 | S3 Vectors index | 1024 dimensions, float32, cosine, non-filterable metadata keys `AMAZON_BEDROCK_TEXT` and `AMAZON_BEDROCK_METADATA` | Storage only |
| 4 | IAM role for the Knowledge Base | read the bucket, invoke the embedding model, access that one index | Free |
| 5 | Bedrock Knowledge Base | embedding `cohere.embed-multilingual-v3`, vector store = S3 Vectors | No hourly fee expected (verify) |
| 6 | S3 data source | the documents bucket, default chunking | No |
| 7 | (optional) AWS Budget $5 with email alert | alerts only, **not a cap** | Free tier covers it |

Explicitly **not** created: Lambda, API Gateway, Cognito, CloudFront, DynamoDB, OpenSearch,
any NAT or VPC resource, anything that bills by the hour.

Test data: one small synthetic or public-domain PDF (about 10 to 20 pages, a few hundred KB),
plus one second PDF on an unrelated topic for Q6. No real personal or work documents.

## 4. Procedure (about 1 to 2 hours, one sitting)
Exact commands will be written into the teardown/run scripts and shown to the owner first; each
CLI command will be checked against `aws <service> <command> help` before use.

1. Create the documents bucket and upload the test PDF(s). Record time.
2. Create the S3 Vectors bucket and index (settings above).
3. Create the KB service role (scoped to the resources above).
4. Create the Knowledge Base and the S3 data source.
5. Run **one** initial `StartIngestionJob` (required once for an S3 data source). Wait for it to finish.
   Never run it again while a direct ingestion is in progress (documented conflict).
6. Using the real adapter in a short local script (not deployed): `ingest()` the test PDF, then
   poll `index_state()` every 5 s for up to 10 minutes, logging each status with a timestamp (Q1, Q2, Q3).
7. Run 3 to 5 `query()` calls: two on-topic, one unrelated, one in Vietnamese if a Vietnamese PDF
   is included. Save the raw response structure (not the text) (Q4, Q6, Q7).
8. Call `delete()`, poll until `NOT_FOUND`, then repeat the on-topic query and confirm the passage
   no longer supports an answer (Q5).
9. Deliberately run one call with an under-permissioned role to capture the AccessDenied action names (Q8).
10. Run the teardown (section 8) and verify nothing remains.
11. Write the findings, then adjust the adapter, parser, README and plan (task S8).

## 5. Cost estimate (order of magnitude, partly unverified)
Public prices found 2026-11-16 (source: AWS pricing pages):
- S3 Vectors (page quotes **US East**, Singapore not listed): storage $0.06 per GB-month; PUT
  $0.20 per GB uploaded (128 KB minimum per PUT); queries $2.50 per million; query data
  processed $0.004 per TB for the first 100K vectors.
- Embeddings: the Bedrock page only shows an example rate of **$0.0001 per 1,000 input tokens**
  for Cohere Embed (derived from an example, not a listed price).
- Nova Lite and Claude Haiku generation prices: **not obtainable from the page**; unverified.
- Knowledge Bases: the page's index-storage and retrieval fees apply to the *managed* knowledge
  base type, not the self-managed S3 Vectors setup used here; whether `RetrieveAndGenerate` has an
  extra charge is **unverified**.

Estimate for the whole spike (assumptions: 20-page PDF about 15K tokens, about 100 vectors,
about 20 queries of about 4K input and 500 output tokens):

| Item | Estimate | Confidence |
|---|---|---|
| Embedding the PDF | about $0.002 | Medium |
| S3 Vectors storage, PUTs, queries | under $0.01 | Medium (US East prices) |
| S3 storage and requests | under $0.01 | High |
| Generation, 20 queries | under $0.40 even at a pessimistic $3 per million input and $15 per million output tokens; likely far less | Low, price unknown |
| IAM, KB, data source | $0 expected | Medium |
| **Expected total** | **under $0.50** | |
| **Proposed hard stop** | **$2.00; stop and tear down if reached** | |

Leftover risk if teardown is forgotten: tiny S3 and S3 Vectors storage (cents per month), no
hourly components. The first billable step still needs your explicit go, and the figures above
will be re-checked against the Pricing API in Part B (P6) before approval.

## 6. Access and guardrails
- A **separate** spike profile, not the read-only one, whose policy allows create/delete **only**
  on resources named `clouddocs-spike-*` (plus `bedrock:InvokeModel` on the two chosen models and
  `iam:PassRole` for the one KB role). The owner creates it; I do not handle keys or passwords.
- No secrets in files or commits. Script outputs go to the scratchpad; only summaries in chat;
  account ID never pasted.
- Everything tagged; a single tag query must list every spike resource.
- Time box: if any step stalls more than 30 minutes, stop and tear down.
- Stop conditions: unexpected cost above $1, any resource not named `clouddocs-spike-*`, any
  AccessDenied that would require widening the policy beyond what is listed here.

## 7. Outputs
- Findings note answering Q1 to Q9 (in chat and appended to `PLAN.md`).
- Raw status timeline and response-shape sample (no document text) saved in the scratchpad.
- Code or doc changes triggered: possible tweaks to `_STATE_MAP`, the grace window, the parser,
  README IAM table; token logging (B9); the architecture doc's "unverified" markers updated.
- A go or no-go for the Terraform tasks T1 to T3.

## 8. Teardown (written and dry-run before the first create)
Order: delete data source, knowledge base, S3 Vectors index, S3 Vectors bucket, empty and delete
the documents bucket, delete the KB role and policies, delete the optional budget. Then verify:
tag-based resource listing returns nothing, `list-knowledge-bases` shows no spike KB,
`list-vector-buckets` shows no spike bucket, `s3 ls` shows no spike bucket. Teardown is
re-runnable and safe if a create step failed halfway.

## 9. Options
| Option | Pros | Cons |
|---|---|---|
| **A. Manual CLI plus a local script** (described above) | Fast, small, no new files outside `backend/` | Throwaway; many CLI parameters to get right |
| **B. Terraform module for T3 (bucket, index, KB, data source), applied only after owner review** | Reusable for the real stack; teardown is `terraform destroy`; reviewable plan | Needs D5 (edits outside `backend/`); depends on the Terraform AWS provider supporting S3 Vectors knowledge bases (unverified) |
| C. Skip the spike | No cost now | First real test happens inside the full stack; harder to debug |

Recommendation: **B if D5 is granted and the provider supports it, otherwise A.** In both cases
the owner reviews the plan or script output before anything is created.

## 10. Approval checklist (owner)
- [ ] Spike goes ahead, option chosen: A / B
- [ ] Budget ceiling for the spike: $____ (proposed hard stop $2)
- [ ] Cross-region inference allowed: yes / no
- [ ] Spike profile created with the section 6 scope, name: ________
- [ ] Time window: ________
- [ ] I have reviewed the teardown script and the exact create commands
- [ ] Model access for embedding and generation models is enabled in the account

Until every box is ticked, no create, deploy or write call will be made.
