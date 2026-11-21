"""HTTP API with a Cognito JWT authorizer as the default for every route.

Security by default: a new route is protected unless it explicitly opts out
(only GET /health does). Stage-level throttling caps request rate so a leaked
URL or a buggy client cannot generate unbounded Lambda/Bedrock cost.
"""

from __future__ import annotations

from aws_cdk import Aws, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_events
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from .backend_code import ARCHITECTURE, RUNTIME, backend_code
from .config import Config
from .ingestion import WORKER_TIMEOUT


class Api(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: Config,
        allowed_origins: list[str],
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
        documents_table: dynamodb.ITable,
        documents_bucket: s3.IBucket,
        knowledge_base_id: str,
        knowledge_base_arn: str,
        data_source_id: str,
        ingest_queue: sqs.IQueue,
    ) -> None:
        super().__init__(scope, construct_id)
        self._code = backend_code()

        self.http_api = apigw.HttpApi(
            self,
            "HttpApi",
            create_default_stage=False,
            default_authorizer=authorizers.HttpUserPoolAuthorizer(
                "CognitoAuthorizer", user_pool, user_pool_clients=[user_pool_client]
            ),
            cors_preflight=apigw.CorsPreflightOptions(
                allow_origins=allowed_origins,
                allow_methods=[
                    apigw.CorsHttpMethod.GET,
                    apigw.CorsHttpMethod.POST,
                    apigw.CorsHttpMethod.DELETE,
                ],
                allow_headers=["authorization", "content-type"],
                max_age=Duration.hours(1),
            ),
        )
        self.stage = apigw.HttpStage(
            self,
            "DefaultStage",
            http_api=self.http_api,
            auto_deploy=True,
            throttle=apigw.ThrottleSettings(
                rate_limit=config.throttle_rate_limit,
                burst_limit=config.throttle_burst_limit,
            ),
        )

        health = self._function("Health", "clouddocs.handlers.health.handler")
        me = self._function("Me", "clouddocs.handlers.me.handler")
        self.functions: dict[str, lambda_.IFunction] = {"Health": health, "Me": me}

        self.http_api.add_routes(
            path="/health",
            methods=[apigw.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration("HealthIntegration", health),
            authorizer=apigw.HttpNoneAuthorizer(),  # public, returns no data
        )
        self.http_api.add_routes(
            path="/me",
            methods=[apigw.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration("MeIntegration", me),
        )

        # Documents API (Phase 2; DELETE added in Phase 5, P5-01).
        self.documents_fn = self._function(
            "Documents",
            "clouddocs.handlers.documents.handler",
            environment={
                "DOCUMENTS_TABLE": documents_table.table_name,
                "DOCUMENTS_BUCKET": documents_bucket.bucket_name,
                "KNOWLEDGE_BASE_ID": knowledge_base_id,
                "DATA_SOURCE_ID": data_source_id,
            },
        )
        self.functions["Documents"] = self.documents_fn
        self._grant_documents_access(self.documents_fn, documents_table, documents_bucket)
        self.documents_fn.add_to_role_policy(
            iam.PolicyStatement(
                # Per-document ingestion, status and removal on this Knowledge Base only (D-006).
                # AWS authorizes IngestKnowledgeBaseDocuments as bedrock:StartIngestionJob
                # (found in the Phase 3 demo: AccessDenied without it).
                actions=[
                    "bedrock:StartIngestionJob",
                    "bedrock:IngestKnowledgeBaseDocuments",
                    "bedrock:GetKnowledgeBaseDocuments",
                    "bedrock:DeleteKnowledgeBaseDocuments",
                ],
                resources=[knowledge_base_arn],
            )
        )
        docs_integration = integrations.HttpLambdaIntegration("DocumentsIntegration", self.documents_fn)
        for method, path in [
            (apigw.HttpMethod.POST, "/documents/upload-url"),
            (apigw.HttpMethod.POST, "/documents/{id}/complete"),
            (apigw.HttpMethod.GET, "/documents"),
            (apigw.HttpMethod.GET, "/documents/{id}"),
            (apigw.HttpMethod.DELETE, "/documents/{id}"),
        ]:
            self.http_api.add_routes(path=path, methods=[method], integration=docs_integration)

        # Chat API (Phase 4): grounded answers from the caller's own documents.
        region = Stack.of(self).region
        profile_id = config.generation_model
        model_id = profile_id.split(".", 1)[1] if profile_id.startswith(("apac.", "us.", "eu.", "global.")) else profile_id
        profile_arn = f"arn:{Aws.PARTITION}:bedrock:{region}:{Aws.ACCOUNT_ID}:inference-profile/{profile_id}"
        self.chat_fn = self._function(
            "Chat",
            "clouddocs.handlers.chat.handler",
            environment={
                "DOCUMENTS_TABLE": documents_table.table_name,
                "DOCUMENTS_BUCKET": documents_bucket.bucket_name,
                "KNOWLEDGE_BASE_ID": knowledge_base_id,
                "DATA_SOURCE_ID": data_source_id,
                "MODEL_ARN": profile_arn,
            },
            timeout=Duration.seconds(29),  # API Gateway's integration limit is 30 s
        )
        self.functions["Chat"] = self.chat_fn
        # Citations are checked against the caller's own documents: read-only, single items.
        documents_table.grant(self.chat_fn, "dynamodb:GetItem")
        self.chat_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
                resources=[knowledge_base_arn],
            )
        )
        self.chat_fn.add_to_role_policy(
            iam.PolicyStatement(
                # The APAC inference profile routes to the same model in several APAC Regions,
                # so the model ARN uses a Region wildcard but names exactly one model.
                actions=["bedrock:InvokeModel"],
                resources=[profile_arn, f"arn:{Aws.PARTITION}:bedrock:*::foundation-model/{model_id}"],
            )
        )
        self.chat_fn.add_to_role_policy(
            iam.PolicyStatement(
                # RetrieveAndGenerate reads the profile before invoking it (found in the
                # Phase 4 demo: AccessDenied "Not authorized to call GetInferenceProfile").
                actions=["bedrock:GetInferenceProfile"],
                resources=[profile_arn],
            )
        )
        self.http_api.add_routes(
            path="/chat/query",
            methods=[apigw.HttpMethod.POST],
            integration=integrations.HttpLambdaIntegration("ChatIntegration", self.chat_fn),
        )

        # Ingestion worker: verifies and indexes each upload reported by S3 through the queue.
        self.worker_fn = self._function(
            "Worker",
            "clouddocs.handlers.ingest_worker.handler",
            environment={
                "DOCUMENTS_TABLE": documents_table.table_name,
                "DOCUMENTS_BUCKET": documents_bucket.bucket_name,
                "KNOWLEDGE_BASE_ID": knowledge_base_id,
                "DATA_SOURCE_ID": data_source_id,
            },
            timeout=WORKER_TIMEOUT,
        )
        self.functions["Worker"] = self.worker_fn
        self._grant_worker_access(self.worker_fn, documents_table, documents_bucket, knowledge_base_arn)
        self.worker_fn.add_event_source(
            lambda_events.SqsEventSource(
                ingest_queue,
                batch_size=5,
                report_batch_item_failures=True,  # retry only the messages that failed
                max_concurrency=2,  # keep Knowledge Base ingest calls gentle
            )
        )

    @staticmethod
    def _grant_worker_access(
        fn: lambda_.IFunction, table: dynamodb.ITable, bucket: s3.IBucket, knowledge_base_arn: str
    ) -> None:
        """Only what verify + ingest needs: a strict subset of the documents Lambda's access."""
        table.grant(fn, "dynamodb:GetItem", "dynamodb:UpdateItem")
        fn.add_to_role_policy(
            iam.PolicyStatement(
                # GetObject: size + first bytes (PDF check). DeleteObject: remove a fake PDF.
                actions=["s3:GetObject", "s3:DeleteObject"],
                resources=[bucket.arn_for_objects("uploads/*.pdf")],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                # The <key>.pdf.metadata.json sidecar that carries the owner's userId.
                actions=["s3:PutObject"],
                resources=[bucket.arn_for_objects("uploads/*.pdf.metadata.json")],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                # Without ListBucket, S3 answers 403 instead of 404 for a missing object.
                actions=["s3:ListBucket"],
                resources=[bucket.bucket_arn],
                conditions={"StringLike": {"s3:prefix": ["uploads/*"]}},
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                # IngestKnowledgeBaseDocuments is authorized as bedrock:StartIngestionJob.
                actions=["bedrock:StartIngestionJob", "bedrock:IngestKnowledgeBaseDocuments"],
                resources=[knowledge_base_arn],
            )
        )

    @property
    def url(self) -> str:
        return self.stage.url

    @staticmethod
    def _grant_documents_access(
        fn: lambda_.IFunction, table: dynamodb.ITable, bucket: s3.IBucket
    ) -> None:
        """Least privilege: only the item operations the repository uses, only the uploads/ prefix."""
        table.grant(
            fn,
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
            "dynamodb:DeleteItem",
            "dynamodb:Query",
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                # PutObject: the presigned POST is signed with this role's credentials,
                # and the Lambda writes the <key>.metadata.json sidecar (Phase 3).
                # GetObject: HeadObject + reading the first bytes (PDF check).
                actions=["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
                resources=[bucket.arn_for_objects("uploads/*")],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                # Without ListBucket, S3 answers 403 instead of 404 for a missing object.
                actions=["s3:ListBucket"],
                resources=[bucket.bucket_arn],
                conditions={"StringLike": {"s3:prefix": ["uploads/*"]}},
            )
        )

    def _function(
        self,
        name: str,
        handler: str,
        environment: dict[str, str] | None = None,
        timeout: Duration | None = None,
    ) -> lambda_.Function:
        log_group = logs.LogGroup(
            self,
            f"{name}Logs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        return lambda_.Function(
            self,
            f"{name}Function",
            runtime=RUNTIME,
            architecture=ARCHITECTURE,
            handler=handler,
            code=self._code,
            memory_size=512 if name in ("Documents", "Chat") else 256,
            timeout=timeout or Duration.seconds(10),
            log_group=log_group,
            logging_format=lambda_.LoggingFormat.JSON,
            environment=environment or {},
        )
