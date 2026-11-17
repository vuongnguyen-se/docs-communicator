# Project Requirements

## 1. Product summary

CloudDocs AI lets a user upload PDF documents and ask questions whose answers are grounded in the uploaded material.

## 2. Target user

A small number of admin-created users (portfolio MVP). Every user signs in through Amazon Cognito. Self sign-up is disabled. Data access and retrieval are scoped to the signed-in user.

## 3. MVP functional requirements

### Document management
- Upload a PDF using a short-lived S3 presigned POST (size and type enforced by the S3 policy).
- Validate file extension, content type, and configured maximum file size.
- Record document metadata and processing status.
- List uploaded documents.
- Show statuses such as `UPLOADED`, `INDEXING`, `READY`, and `FAILED`.
- Allow deletion of a document and its metadata. Define and implement the corresponding Knowledge Base cleanup behavior before claiming full deletion.

### Question answering
- Accept a natural-language question.
- Call Amazon Bedrock Knowledge Bases `RetrieveAndGenerate`.
- Return the answer and source references/citations supplied by the service.
- Handle no-relevant-source responses gracefully.
- Display loading, error, and empty states in the frontend.

### Basic operational requirements
- Log request correlation IDs and useful error details without logging document contents, credentials, or sensitive user data.
- Return consistent JSON error responses.
- Keep secrets and environment-specific configuration outside source code.

## 4. MVP exclusions

- No public sharing of uploaded documents.
- No public self sign-up.
- No custom model training or fine-tuning.
- No autonomous agents or tool execution.
- No promise that generated answers are always correct.
- No production compliance certification.
- No complex analytics dashboard.

## 5. Non-functional requirements

- Security: Cognito authentication on all non-health endpoints, private S3 buckets, least-privilege IAM, HTTPS, input validation.
- Reliability: clear processing states and retry-safe operations.
- Maintainability: small modules, typed API contracts, tests, documented configuration.
- Cost: ephemeral environments (destroy after each session), bounded file size, small test corpus, budget alerts, resource cleanup instructions.
- Usability: explain when a document is still processing and when no source was found.

## 6. Acceptance criteria

The MVP is acceptable when:
1. The frontend can request an upload URL and upload a test PDF to private S3.
2. The backend records document metadata in DynamoDB.
3. The document can be ingested by the configured Bedrock Knowledge Base.
4. The UI can show whether ingestion is complete.
5. A question can be submitted and answered through `RetrieveAndGenerate`.
6. The response includes source references when returned by Bedrock.
7. Invalid requests return useful 4xx errors.
8. Logs are available in CloudWatch.
9. The README explains deployment, configuration, testing, and cleanup.
10. No AWS credentials or secrets are committed.
11. Unauthenticated API calls are rejected, and one user cannot see or retrieve another user's documents.
12. `cdk destroy` plus the teardown check leave no tagged resources behind.
