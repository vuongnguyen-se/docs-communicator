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
- `docs/aws-account-setup.md`: one-time AWS account, CLI and budget setup.

## Run the tests locally

```bash
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]" && .venv/Scripts/python -m pytest
cd frontend && npm ci && npm test && npm run dev   # dev server uses the in-memory mock API
```
- `PROMPT_FOR_CODING_AGENT.md`: initial prompt to paste into your coding platform.

## Important implementation notes

- Confirm service and model availability in the chosen AWS Region before provisioning.
- Bedrock Knowledge Bases requires a supported embedding model and a supported vector store configuration. Do not assume every vector-store option is available in every Region.
- Keep AWS account IDs, credentials, API keys, and other secrets out of source control.
- Use least-privilege IAM policies and separate development resources from production resources.
- Do not claim that an answer is supported by a source unless the retrieval response actually provides that source.
