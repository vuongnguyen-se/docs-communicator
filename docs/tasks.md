# CloudDocs AI — Phase Checklist

Rule: one milestone at a time; no AWS provisioning without explicit approval.

## Phase 0 — Discovery (this milestone)
- [x] Inspect repo (only the spec existed), `git init`, copy spec to `PROJECT_SPEC.md`
- [x] Compatibility check for ap-southeast-1 (see `architecture.md` §1)
- [x] `docs/architecture.md`
- [x] `docs/cost-estimate.md` (prices still unverified)
- [x] This checklist
- [x] Document languages: English + Vietnamese → Cohere Embed Multilingual v3
- [ ] Owner answers remaining open question: cross-region inference acceptable? (architecture.md §9, Q2)
- [ ] Owner fills price figures / approves budget ceiling
- [ ] Add `.gitignore`, initial commit (after owner OKs)

## Phase 1 — Local MVP (no AWS credentials)
- [x] Repo scaffold: `backend/` (frontend/infrastructure pending)
- [x] Backend: pydantic models, config, error model, status state machine
- [x] Backend: service interfaces (storage, metadata, knowledge base) + fakes
- [x] Handlers: upload-url, complete, list, get, delete, chat/query, health
- [x] Validators (type, size, key, question length) + owner-from-JWT helper
- [x] RAG response parser: citations only from retrieved references
- [x] pytest with in-memory fakes (57 tests passing)
- [ ] Frontend: Vite + React + TS, login stub, upload, list, chat UI, mock API mode
- [ ] ESLint + `npm run build` + ruff/mypy pass locally
- [ ] API contract examples in `docs/`

## Phase 2 — AWS infrastructure and RAG (needs explicit approval to deploy)
- [ ] Read-only pre-flight: model access, inference profile IDs, KB/S3 Vectors in ap-southeast-1
- [ ] Spike: direct-ingestion API shape and document status values
- [ ] Terraform: S3 (docs, web), CloudFront + OAC, Cognito (no self-signup), HTTP API + JWT authorizer
- [ ] Terraform: Lambdas + least-privilege IAM, DynamoDB, CloudWatch log groups/alarms
- [ ] Terraform: S3 Vectors bucket/index, Bedrock KB + S3 data source + service role
- [ ] `terraform plan` reviewed by owner → approved apply
- [ ] Manual smoke test: login → upload → INDEXING → READY → ask → cited answer → delete
- [ ] Unrelated question returns no fabricated citation
- [ ] Vietnamese PDF + Vietnamese question and cross-language question tested; compare Nova Lite vs Claude Haiku
- [ ] Teardown rehearsal (`terraform destroy`)

## Phase 3 — DevOps hardening
- [ ] GitHub Actions `ci.yml`: ruff, pytest, eslint, build, terraform fmt/validate, tfsec/checkov
- [ ] `deploy.yml` with environment approval and GitHub OIDC role
- [ ] CloudWatch dashboard, runbook, security + cost review
- [ ] README: architecture, security design, cost caveats, teardown, screenshots

## Phase 4 — Optional (only after MVP works)
- [ ] SQS + DLQ ingestion queue, Step Functions status polling
- [ ] Multi-user isolation via metadata filter + two-user authorization test
- [ ] Guardrails / prompt-injection evals
- [ ] Measured trade-offs (cost, latency, concurrency)
