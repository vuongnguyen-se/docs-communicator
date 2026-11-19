"""RAG layer: Bedrock Knowledge Base on S3 Vectors (Phase 3, D-005..D-008).

Mirrors the setup proven in spike P0-07 (docs/spikes/2026-11-19-knowledge-base-spike.md):
- S3 Vectors index: float32, 1024 dims (Cohere Embed Multilingual v3), cosine; the
  Bedrock text/metadata keys are non-filterable so only our own keys (userId,
  documentId) are filterable.
- Knowledge Base role: trusted only by Bedrock in this account; may read only the
  uploads/ prefix, use only this index and call only the embedding model.
- S3 data source on uploads/, fixed-size chunks (300 tokens, 20% overlap),
  vectors deleted with the data source.
- The required first sync runs once at deploy (custom resource). Documents are
  then added one at a time by the documents Lambda (direct ingestion).
"""

from __future__ import annotations

from aws_cdk import Aws, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3vectors
from aws_cdk import custom_resources as cr
from constructs import Construct

EMBEDDING_MODEL_ID = "cohere.embed-multilingual-v3"
EMBEDDING_DIMENSIONS = 1024
UPLOADS_PREFIX = "uploads/"


class Knowledge(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, documents_bucket: s3.IBucket) -> None:
        super().__init__(scope, construct_id)
        region = Stack.of(self).region
        embedding_model_arn = f"arn:{Aws.PARTITION}:bedrock:{region}::foundation-model/{EMBEDDING_MODEL_ID}"

        # ---- vector store
        self.vector_bucket = s3vectors.CfnVectorBucket(self, "VectorBucket")
        self.vector_bucket.apply_removal_policy(RemovalPolicy.DESTROY)
        self.index = s3vectors.CfnIndex(
            self,
            "VectorIndex",
            vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
            index_name="kb-index",
            data_type="float32",
            dimension=EMBEDDING_DIMENSIONS,
            distance_metric="cosine",
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
            ),
        )
        self.index.apply_removal_policy(RemovalPolicy.DESTROY)

        # ---- Knowledge Base service role (least privilege)
        self.role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID},
                    "ArnLike": {"aws:SourceArn": f"arn:{Aws.PARTITION}:bedrock:{region}:{Aws.ACCOUNT_ID}:knowledge-base/*"},
                },
            ),
            description="CloudDocs AI Knowledge Base: read uploads/, use one vector index, call the embedding model",
        )
        policy = iam.Policy(
            self,
            "KnowledgeBasePolicy",
            statements=[
                iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[embedding_model_arn]),
                iam.PolicyStatement(
                    actions=["s3:GetObject"],
                    resources=[documents_bucket.arn_for_objects(f"{UPLOADS_PREFIX}*")],
                    conditions={"StringEquals": {"aws:ResourceAccount": Aws.ACCOUNT_ID}},
                ),
                iam.PolicyStatement(
                    actions=["s3:ListBucket"],
                    resources=[documents_bucket.bucket_arn],
                    conditions={
                        "StringEquals": {"aws:ResourceAccount": Aws.ACCOUNT_ID},
                        "StringLike": {"s3:prefix": [f"{UPLOADS_PREFIX}*"]},
                    },
                ),
                iam.PolicyStatement(
                    actions=[
                        "s3vectors:PutVectors",
                        "s3vectors:GetVectors",
                        "s3vectors:DeleteVectors",
                        "s3vectors:QueryVectors",
                        "s3vectors:GetIndex",
                    ],
                    resources=[self.index.attr_index_arn],
                ),
            ],
        )
        policy.attach_to_role(self.role)

        # ---- Knowledge Base + S3 data source
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=f"{Stack.of(self).stack_name}-kb",
            role_arn=self.role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_model_arn
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=self.index.attr_index_arn
                ),
            ),
        )
        self.knowledge_base.node.add_dependency(policy)  # role must work before Bedrock validates it
        self.knowledge_base.apply_removal_policy(RemovalPolicy.DESTROY)

        self.data_source = bedrock.CfnDataSource(
            self,
            "DocumentsDataSource",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            name="documents-s3",
            data_deletion_policy="DELETE",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=documents_bucket.bucket_arn,
                    inclusion_prefixes=[UPLOADS_PREFIX],
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=300, overlap_percentage=20
                    ),
                ),
            ),
        )
        self.data_source.apply_removal_policy(RemovalPolicy.DESTROY)

        # ---- P3-02: required first sync, once, at deploy time (bucket is empty then: fast)
        sync = cr.AwsCustomResource(
            self,
            "InitialSync",
            on_create=cr.AwsSdkCall(
                service="bedrock-agent",
                action="StartIngestionJob",
                parameters={
                    "knowledgeBaseId": self.knowledge_base.attr_knowledge_base_id,
                    "dataSourceId": self.data_source.attr_data_source_id,
                    "description": "Initial sync required before direct ingestion (D-006)",
                },
                physical_resource_id=cr.PhysicalResourceId.of("initial-sync"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=["bedrock:StartIngestionJob"],
                        resources=[self.knowledge_base.attr_knowledge_base_arn],
                    )
                ]
            ),
            log_group=logs.LogGroup(
                self, "InitialSyncLogs", retention=logs.RetentionDays.ONE_WEEK, removal_policy=RemovalPolicy.DESTROY
            ),
            install_latest_aws_sdk=False,
        )
        sync.node.add_dependency(self.data_source)

    @property
    def knowledge_base_id(self) -> str:
        return self.knowledge_base.attr_knowledge_base_id

    @property
    def knowledge_base_arn(self) -> str:
        return self.knowledge_base.attr_knowledge_base_arn

    @property
    def data_source_id(self) -> str:
        return self.data_source.attr_data_source_id
