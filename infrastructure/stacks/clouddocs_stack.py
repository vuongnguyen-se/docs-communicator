"""Single stack for the whole environment, so `cdk destroy` removes everything at once (D-002)."""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from .api import Api
from .auth import Auth
from .config import Config


class CloudDocsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, config: Config, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        auth = Auth(self, "Auth")
        api = Api(
            self,
            "Api",
            config=config,
            user_pool=auth.user_pool,
            user_pool_client=auth.client,
        )

        # Non-secret identifiers the frontend needs (copied into frontend/.env.local).
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "UserPoolId", value=auth.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=auth.client.user_pool_client_id)
        CfnOutput(self, "Region", value=self.region)
