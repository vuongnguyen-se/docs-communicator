# Cost notes (from the real bill)

**Headline:** building and demoing CloudDocs AI cost **under one US cent** in AWS usage from 17 to 20 November 2026. That period covered the first deploys of Phases 1–4, the Knowledge Base spike, the MVP evaluation and the owner's browser tests.

Source: AWS Cost Explorer, `UnblendedCost` grouped by usage type for 2026-11-17 to 2026-11-21. Cost Explorer lags by about a day, so the three demos run on 21 November (P5-07, P5-08, P6-01) are not in these figures yet. See "Refresh these numbers" below.

## Where the money went (17–20 November 2026)

| Service | What was used | Cost (USD) |
|---|---|---|
| S3 Vectors | 98 vector requests and the index writes | 0.0033 |
| S3 | 1,467 requests (uploads, deploys of the website, sidecar files) | 0.0021 |
| Bedrock: Nova Lite | input and output tokens for answers | 0.0017 |
| Bedrock: Cohere Embed | embeddings for the uploaded PDFs and the questions | 0.0004 |
| API Gateway | 127 HTTP API requests | 0.0002 |
| DynamoDB | 142 reads and 56 writes (on demand) | 0.0001 |
| Lambda, SQS, SNS, CloudWatch, Cognito, CloudFront | within the free tier | 0.0000 |
| **Total** | | **≈ 0.008** |

Not counted above, because they are not part of this project: an EBS snapshot and an AWS Amplify app from other work in the same account, and the monthly tax line.

## Why it is this cheap

- **Ephemeral environments (D-002).** The stack exists only during a working session (about an hour), then `scripts/destroy.ps1` deletes it and checks that nothing tagged `Project=CloudDocsAI` is left. Between sessions only the CDK bootstrap stack remains.
- **No idle cost anywhere.** Every service is billed per request or per token: Lambda, API Gateway, DynamoDB on demand, SQS, and S3 Vectors as the vector store (D-007). A vector store with a running cluster, such as OpenSearch Serverless, would have cost far more per hour than this project's whole bill.
- **Small, fast models.** Nova Lite answers through the `apac.` inference profile, and Cohere Embed Multilingual v3 covers both English and Vietnamese (D-008).
- **Guardrails and WAF are off on purpose.** Each has a fixed or per-request price that a demo doesn't justify; D-016 and D-017 list the triggers for turning them on.
- **A budget** (`clouddocs-monthly`, USD 10, P0-03) emails the owner at 50% and 100% of actual spend and at 80% of the forecast.

## What a real deployment would add

These are not measured yet; check the current prices before relying on them.

- Always-on usage: the same per-request prices, multiplied by real traffic. Nothing is billed while idle, except S3 storage for the PDFs and vectors.
- Optional extras with their own price: Bedrock Guardrails (D-016), AWS WAF (D-017), a custom domain (Route 53 hosted zone and certificate).

## Refresh these numbers

Cost Explorer charges USD 0.01 per API request. These two calls give the total per service and the cost of each usage type:

```powershell
aws ce get-cost-and-usage --profile clouddocs-dev --time-period Start=2026-11-17,End=<tomorrow> `
  --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE
aws ce get-cost-and-usage --profile clouddocs-dev --time-period Start=2026-11-17,End=<tomorrow> `
  --granularity MONTHLY --metrics UnblendedCost UsageQuantity --group-by Type=DIMENSION,Key=USAGE_TYPE
```

The `Project` cost allocation tag was activated on 2026-11-21 (P0-04), so from then on `--group-by Type=TAG,Key=Project` separates this project from other work in the account without manual filtering.
