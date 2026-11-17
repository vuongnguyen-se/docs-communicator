# Security and Cost Baseline

## Security

### Identity and access
- Use Lambda execution roles, not static AWS credentials.
- Scope each role to only the required actions and resources.
- Keep separate roles for document operations, chat operations, and infrastructure deployment where practical.
- Cognito is required before the first public deploy; self sign-up disabled (D-004).
- Once authentication exists, derive user identity from verified authorizer claims, not a user ID supplied in the request body.

### S3
- Block public access.
- Enable encryption at rest.
- Use TLS for requests.
- Use narrow, short-lived presigned URLs.
- Generate object keys on the backend; do not trust arbitrary client-provided keys.
- Configure lifecycle cleanup for abandoned test uploads where appropriate.
- Define deletion behavior for both S3 objects and Knowledge Base indexed content.

### API
- Validate input size and format.
- Configure CORS for the actual frontend origin; CORS is not authorization.
- Configure throttling and sensible quotas.
- Avoid exposing internal exception messages or stack traces.
- Do not log presigned URLs or sensitive user content.

### RAG and AI
- Treat document content and retrieved passages as untrusted data.
- Consider prompt injection in uploaded documents.
- Use clear system instructions and constrain the model to retrieved context.
- Consider Bedrock Guardrails after the baseline flow works.
- Evaluate responses against known questions and expected source passages.

## Cost controls

- **Ephemeral environments (D-002):** deploy only for a working session, then `cdk destroy` and run the teardown check. Nothing should stay running between sessions except the budget and the CDK bootstrap stack.
- Prefer a vector store without idle cost (S3 Vectors). Avoid OpenSearch Serverless for this project unless nothing else is supported.
- Tag every resource `Project=CloudDocsAI`.

- Start with a small number of short PDF test files.
- Use on-demand DynamoDB capacity for a low-traffic prototype.
- Set AWS Budgets and billing alerts.
- Review S3 storage, API Gateway requests, Lambda duration, Bedrock model inference, Knowledge Base ingestion, and vector storage charges.
- Avoid always-on infrastructure unless needed.
- Delete test Knowledge Bases, vector stores, buckets, tables, and other billable resources when finished.
- Remember that deleting a frontend does not automatically delete backend resources.
- Check current AWS pricing in the selected Region before deploying. Do not rely on fixed estimates in this document.

## Before every deployment

- [ ] Confirm AWS account and Region.
- [ ] Review resources that will be created or changed.
- [ ] Review IAM policy changes.
- [ ] Check expected charges.
- [ ] Confirm no secrets are committed.
- [ ] Know how to tear down the environment.

## After every session

- [ ] `cdk destroy` completed without errors.
- [ ] Teardown check shows no `Project=CloudDocsAI` resources.
- [ ] Session log row added in `TASKS.md`.

## Public repository

The GitHub repository is public. Never commit account IDs, `.env` files, `cdk.context.json`, or `cdk.out/`.
