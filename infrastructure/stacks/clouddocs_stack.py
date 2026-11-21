"""Single stack for the whole environment, so `cdk destroy` removes everything at once (D-002)."""

from __future__ import annotations

from typing import Any

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from .api import Api
from .auth import Auth
from .config import Config
from .data import Data
from .ingestion import Ingestion
from .knowledge import Knowledge
from .monitoring import Monitoring
from .web import Web


class CloudDocsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, config: Config, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        auth = Auth(self, "Auth")
        # Web first: the API's CORS needs the CloudFront domain.
        web = Web(self, "Web", region=config.region)
        origins = [*config.allowed_origins, web.url]
        data = Data(self, "Data", allowed_origins=origins)
        knowledge = Knowledge(self, "Knowledge", documents_bucket=data.bucket)
        ingestion = Ingestion(self, "Ingestion", documents_bucket=data.bucket)
        api = Api(
            self,
            "Api",
            config=config,
            allowed_origins=origins,
            user_pool=auth.user_pool,
            user_pool_client=auth.client,
            documents_table=data.table,
            documents_bucket=data.bucket,
            knowledge_base_id=knowledge.knowledge_base_id,
            knowledge_base_arn=knowledge.knowledge_base_arn,
            data_source_id=knowledge.data_source_id,
            ingest_queue=ingestion.queue,
        )
        Monitoring(
            self,
            "Monitoring",
            functions=api.functions,
            http_api=api.http_api,
            chat_function=api.chat_fn,
            dead_letter_queue=ingestion.dead_letter_queue,
            alarm_email=config.alarm_email,
        )
        web.deploy_site(
            {
                "mode": "http",
                "apiUrl": api.url,
                "region": self.region,
                "userPoolId": auth.user_pool.user_pool_id,
                "userPoolClientId": auth.client.user_pool_client_id,
            }
        )

        # Non-secret identifiers (also served to the browser as /config.json).
        CfnOutput(self, "WebUrl", value=web.url)
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "UserPoolId", value=auth.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=auth.client.user_pool_client_id)
        CfnOutput(self, "Region", value=self.region)
        CfnOutput(self, "KnowledgeBaseId", value=knowledge.knowledge_base_id)
        CfnOutput(self, "DataSourceId", value=knowledge.data_source_id)
