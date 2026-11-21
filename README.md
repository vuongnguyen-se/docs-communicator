# CloudDocs AI

**CloudDocs AI** is a serverless, AI-powered document assistant on AWS. Users upload PDF documents and ask natural-language questions. The application retrieves relevant passages from those documents and uses Amazon Bedrock to generate grounded answers with source references.

## Product goal

Build a portfolio-quality cloud application that demonstrates:
- Serverless application architecture on AWS.
- Generative AI integration using Amazon Bedrock.
- Retrieval-Augmented Generation (RAG).
- Secure document upload and data access.
- Asynchronous document ingestion.
- Monitoring, cost awareness, and Infrastructure as Code.

## MVP user journey

1. A user opens the React web application and signs in (Amazon Cognito; accounts are created by the admin).
2. The user uploads a PDF through a secure, time-limited S3 presigned URL.
3. The document is stored in the application's S3 upload bucket/prefix.
4. The application starts or schedules ingestion into an Amazon Bedrock Knowledge Base.
5. The user asks a question about their documents.
6. The backend calls Bedrock Knowledge Bases `RetrieveAndGenerate`.
7. The UI displays the generated answer and available source citations.

## Initial technology choices

- Frontend: React + TypeScript + Vite.
- Region: `ap-southeast-1` (Singapore).
- Hosting: Amazon S3 + CloudFront.
- Authentication: Amazon Cognito User Pool + API Gateway JWT authorizer.
- API: Amazon API Gateway (HTTP API).
- Compute: AWS Lambda using Python.
- Document storage: Amazon S3.
- Metadata and chat history: Amazon DynamoDB.
- RAG: Amazon Bedrock Knowledge Bases.
- Model access: Amazon Bedrock embedding model + text generation model, selected from models available in the target AWS Region.
- Observability: Amazon CloudWatch.
- Vector store: Amazon S3 Vectors preferred (to be verified in the Region; see `DECISIONS.md` D-007).
- IaC: AWS CDK (Python), from Phase 1.
- Environments are ephemeral: deploy, demo, then `cdk destroy`.

## Scope discipline

Build the MVP first. Do not add microservices, EKS/Kubernetes, multi-agent workflows, fine-tuning, or a custom vector database unless a documented requirement justifies it.

Cognito authentication is part of the MVP (D-004). SQS-based ingestion, Step Functions, Bedrock Guardrails, CI/CD, and richer monitoring are planned enhancements—not MVP assumptions.

## Documentation map

- `PROJECT_REQUIREMENTS.md`: features, non-functional requirements, and acceptance criteria.
- `ARCHITECTURE.md`: components, data flows, trust boundaries, and architecture decisions.
- `TECH_STACK.md`: languages, frameworks, and service choices.
- `DATABASE_DESIGN.md`: DynamoDB entities and access patterns.
- `API_SPECIFICATION.md`: API contract.
- `DEVELOPMENT_ROADMAP.md`: phased implementation plan.
- `AI_CODING_RULES.md`: instructions for AI coding assistants.
- `SECURITY_AND_COST.md`: security baseline and cost controls.
- `TASKS.md`: implementation checklist and progress tracker.
- `DECISIONS.md`: architecture decision log.
- `docs/HOW_IT_WORKS.md`: **start here**: architecture, flows, stages and current status.
- `docs/aws-account-setup.md`: one-time AWS account, CLI and budget setup.

## Run the tests locally

```bash
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]" && .venv/Scripts/python -m pytest
cd frontend && npm ci && npm test && npm run dev   # dev server uses the in-memory mock API
cd infrastructure && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest
```

GitHub Actions runs the same checks, plus `ruff`, `mypy`, `eslint`, the frontend build and `cdk synth`, on every pull request and push to `main` (`.github/workflows/ci.yml`). It uses no AWS credentials.

## Deploy and tear down (PowerShell, after `docs/aws-account-setup.md`)

```powershell
aws sso login --profile clouddocs-dev
powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1
powershell -ExecutionPolicy Bypass -File scripts\create-user.ps1 -Email you@example.com
# ... demo ...
powershell -ExecutionPolicy Bypass -File scripts\destroy.ps1   # always, at the end of the session
```

Options:
- `deploy.ps1 -AlarmEmail you@example.com`: subscribes that address to the CloudWatch alarms. Confirm the subscription email.
- `deploy.ps1 -RequireApproval never` and `destroy.ps1 -Force`: skip the interactive confirmations, for runs without a terminal (for example an automation agent). Only use them after the IAM review in `docs/iam-review.md`.
- The scripts use `infrastructure\.venv`, or `infrastructure\venv` if that is what exists.
- `PROMPT_FOR_CODING_AGENT.md`: initial prompt to paste into your coding platform.

## Configuration

Nothing secret is configured anywhere: AWS access comes from your SSO login (`aws sso login --profile clouddocs-dev`), and the Lambdas use their IAM roles.

| Where | Setting | Default | Notes |
|---|---|---|---|
| `infrastructure/cdk.json` → `context.clouddocs` | `region` | `ap-southeast-1` | D-001 |
| | `allowedOrigins` | `["http://localhost:5173"]` | Extra CORS origins; the CloudFront URL is added automatically |
| | `throttleRateLimit` / `throttleBurstLimit` | `5` / `10` | API Gateway limits per second |
| | `generationModel` | `apac.amazon.nova-lite-v1:0` | Bedrock inference profile used for answers (D-008) |
| Lambda environment (set by CDK) | `DOCUMENTS_TABLE`, `DOCUMENTS_BUCKET`, `KNOWLEDGE_BASE_ID`, `DATA_SOURCE_ID`, `MODEL_ARN` | — | Never set by hand |
| Lambda environment (optional) | `MAX_FILE_BYTES`, `MAX_DOCUMENTS`, `MAX_QUESTION_CHARS`, `UPLOAD_URL_TTL_SECONDS` | 10 MB, 5, 2000, 300 s | `backend/src/clouddocs/config.py` |
| Website | `/config.json` | — | Written at deploy time with the API URL and Cognito IDs (public identifiers) |
| Local frontend | `frontend/.env.local` | mock mode | Copy `frontend/.env.example`; `VITE_API_MODE=mock` needs no AWS |

The embedding model (Cohere Embed Multilingual v3, 1024 dimensions) is fixed in `infrastructure/stacks/knowledge.py`, because changing it means rebuilding the vector index.

## Evaluate answer quality

With a stack deployed:

```bash
python -m pip install -r eval/requirements.txt
python eval/make_pdfs.py eval/out            # fictional English, Vietnamese and prompt-injection PDFs
python eval/run_eval.py eval/out docs/evaluation.md
```

It runs 11 cases (known answers, cross-lingual, unrelated questions, prompt injection, two-user isolation) and writes the report to `docs/evaluation.md`.

## Cost and cleanup

Run `scripts\destroy.ps1` at the end of every session. It deletes the stack and then runs `check-teardown.ps1 -Cleanup`, which removes leftover log groups and fails if anything tagged `Project=CloudDocsAI` remains. Only the `CDKToolkit` bootstrap stack (a few cents a month) is kept between sessions. A demo session costs a few cents (see `TASKS.md` session log).

## Important implementation notes

- Confirm service and model availability in the chosen AWS Region before provisioning.
- Bedrock Knowledge Bases requires a supported embedding model and a supported vector store configuration. Do not assume every vector-store option is available in every Region.
- Keep AWS account IDs, credentials, API keys, and other secrets out of source control.
- Use least-privilege IAM policies and separate development resources from production resources.
- Do not claim that an answer is supported by a source unless the retrieval response actually provides that source.
