"""HTTP API with a Cognito JWT authorizer as the default for every route.

Security by default: a new route is protected unless it explicitly opts out
(only GET /health does). Stage-level throttling caps request rate so a leaked
URL or a buggy client cannot generate unbounded Lambda/Bedrock cost.
"""

from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .backend_code import ARCHITECTURE, RUNTIME, backend_code
from .config import Config


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

        # Documents API (Phase 2). DELETE is wired in Phase 5 once the Knowledge Base exists.
        self.documents_fn = self._function(
            "Documents",
            "clouddocs.handlers.documents.handler",
            environment={
                "DOCUMENTS_TABLE": documents_table.table_name,
                "DOCUMENTS_BUCKET": documents_bucket.bucket_name,
            },
        )
        self._grant_documents_access(self.documents_fn, documents_table, documents_bucket)
        docs_integration = integrations.HttpLambdaIntegration("DocumentsIntegration", self.documents_fn)
        for method, path in [
            (apigw.HttpMethod.POST, "/documents/upload-url"),
            (apigw.HttpMethod.POST, "/documents/{id}/complete"),
            (apigw.HttpMethod.GET, "/documents"),
            (apigw.HttpMethod.GET, "/documents/{id}"),
        ]:
            self.http_api.add_routes(path=path, methods=[method], integration=docs_integration)

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
                # PutObject: the presigned POST is signed with this role's credentials.
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
        self, name: str, handler: str, environment: dict[str, str] | None = None
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
            memory_size=256,
            timeout=Duration.seconds(10),
            log_group=log_group,
            logging_format=lambda_.LoggingFormat.JSON,
            environment=environment or {},
        )
