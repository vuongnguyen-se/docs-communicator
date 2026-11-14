# CloudDocs AI — Cost Estimate (Phase 0)

**Status: UNVERIFIED.** I could not retrieve current ap-southeast-1 price figures for S3 Vectors, Cohere Embed v3 or Nova Lite from the AWS pricing pages during Phase 0, so this document gives the cost *structure* and *drivers* and deliberately does not invent dollar amounts. Before Phase 2, fill the "Unit price" column from the AWS Pricing Calculator / pricing pages for ap-southeast-1.

Budget alerts do **not** cap spend. Nothing is provisioned yet, so current cost is $0.

## Billing model per service

| Service | Billed on | Always-on cost? | Unit price (ap-southeast-1) | MVP usage assumption |
|---|---|---|---|---|
| S3 (frontend + docs) | GB-month, requests | No (tiny) | ⚠️ TBD | ≤ 5 PDFs × 10 MB = ≤ 50 MB |
| CloudFront | Data out, requests | No | ⚠️ TBD (a free tier exists, verify) | Demo traffic |
| Cognito | MAU | No | ⚠️ TBD (1 user) | 1 user |
| API Gateway HTTP API | Per million requests | No | ⚠️ TBD | < 10k requests/month |
| Lambda | Requests + GB-s | No | ⚠️ TBD | < 10k invocations/month |
| DynamoDB on-demand | Read/write units, storage | No | ⚠️ TBD | A few dozen items |
| CloudWatch | Log ingestion/storage, alarms, dashboard | Alarms and dashboards bill monthly | ⚠️ TBD | 2–4 alarms; log retention 14 days |
| S3 Vectors | Storage, PUT (logical GB), queries | No (pay per use) | ⚠️ TBD | A few thousand vectors |
| Bedrock embeddings (Cohere Embed v3) | Input tokens (ingestion + each query) | No | ⚠️ TBD (a third-party listing showed ≈ $0.10 / 1M input tokens; unconfirmed for this region) | 50 MB PDF ≈ low millions of tokens at the very most |
| Bedrock generation (Nova Lite, APAC profile) | Input/output tokens | No | ⚠️ TBD | ~4k input + 500 output tokens per question |
| AWS Budgets | Free for first budgets (verify) | No | ⚠️ TBD | 1 budget |

## Components deliberately avoided (continuously billed)

NAT Gateway, EC2, OpenSearch Serverless (has a minimum OCU charge) or managed OpenSearch, Aurora, Neptune, provisioned throughput, KMS customer-managed keys (monthly per-key fee) in the MVP.

## Estimation method (fill in before deploy)

- Ingestion cost ≈ (total PDF tokens ÷ 1M) × embedding price. Re-ingesting a document pays again.
- Query cost ≈ questions × [(input tokens ÷ 1M) × input price + (output tokens ÷ 1M) × output price + query-embedding tokens × embedding price + S3 Vectors query charge].
- Fixed monthly: CloudWatch alarms/dashboard + S3 storage + vector storage.

Expected shape: for a demo with a handful of PDFs and a few hundred questions the cost should be dominated by CloudWatch alarms and generation tokens, and should be small, but this is **an expectation, not a verified number**.

## Cost controls

1. Hard limits in code: 10 MB/file, 5 files, 2000-char questions, `maxTokens` cap on generation, API Gateway throttling (low burst/rate).
2. AWS Budget with email alerts at 50/80/100% of a small monthly amount (owner to choose).
3. CloudWatch log retention 14 days; S3 lifecycle: abort incomplete multipart uploads after 1 day, expire `uploads/` objects stuck in `PENDING_UPLOAD` after 2 days.
4. `terraform destroy` runbook; vector bucket and S3 buckets need `force_destroy` in dev only.
5. Cross-region inference does not change the per-token price model but check the profile's pricing.

## Pre-deploy checklist

- [ ] Fill every ⚠️ unit price from official pages for ap-southeast-1
- [ ] Run the AWS Pricing Calculator and record the total here
- [ ] Owner approves the monthly ceiling and the budget amount
