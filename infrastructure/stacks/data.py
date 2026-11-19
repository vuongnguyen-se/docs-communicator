"""Document storage: private S3 bucket for PDFs + DynamoDB table for metadata (Phase 2).

- Bucket: never public, TLS only, encrypted. The browser can only write through
  short-lived presigned POST forms issued by the documents Lambda, and CORS lets
  only our own site origins send them.
- Table: PK/SK single-table design from DATABASE_DESIGN.md, on-demand billing
  (pay per request, nothing when idle).
- Both are destroyed with the stack (D-002).
"""

from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class Data(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, allowed_origins: list[str]) -> None:
        super().__init__(scope, construct_id)

        self.bucket = s3.Bucket(
            self,
            "DocumentsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.POST],
                    allowed_origins=allowed_origins,
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
            lifecycle_rules=[s3.LifecycleRule(abort_incomplete_multipart_upload_after=Duration.days(1))],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        self.table = dynamodb.Table(
            self,
            "DocumentsTable",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
