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
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
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
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
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
                allow_origins=config.allowed_origins,
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

    @property
    def url(self) -> str:
        return self.stage.url

    def _function(self, name: str, handler: str) -> lambda_.Function:
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
        )
