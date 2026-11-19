"""Synth-time checks of security and teardown rules. No AWS credentials needed."""

from __future__ import annotations

import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.clouddocs_stack import CloudDocsStack
from stacks.config import config_from_dict


@pytest.fixture(scope="module")
def template() -> Template:
    # Skip Lambda bundling in tests: no pip downloads, fast and offline.
    app = cdk.App(context={"aws:cdk:bundling-stacks": []})
    config = config_from_dict({"allowedOrigins": ["http://localhost:5173"]})
    stack = CloudDocsStack(
        app, "Test", config=config, env=cdk.Environment(account="111111111111", region="ap-southeast-1")
    )
    cdk.Tags.of(app).add("Project", "CloudDocsAI")
    return Template.from_stack(stack)


def test_user_pool_is_admin_only_and_destroyable(template: Template) -> None:
    template.has_resource(
        "AWS::Cognito::UserPool",
        {
            "Properties": Match.object_like(
                {
                    "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
                    "UserPoolTier": "LITE",
                    "DeletionProtection": "INACTIVE",
                }
            ),
            "DeletionPolicy": "Delete",
        },
    )


def test_web_client_has_no_secret(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {"GenerateSecret": False, "PreventUserExistenceErrors": "ENABLED"},
    )


def test_health_is_public_and_me_requires_jwt(template: Template) -> None:
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Route", {"RouteKey": "GET /health", "AuthorizationType": "NONE"}
    )
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Route", {"RouteKey": "GET /me", "AuthorizationType": "JWT"}
    )


def test_every_route_except_health_requires_jwt(template: Template) -> None:
    for route in template.find_resources("AWS::ApiGatewayV2::Route").values():
        props = route["Properties"]
        if props["RouteKey"] != "GET /health":
            assert props.get("AuthorizationType") == "JWT", props["RouteKey"]


def test_stage_is_throttled(template: Template) -> None:
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Stage",
        {
            "StageName": "$default",
            "AutoDeploy": True,
            "DefaultRouteSettings": {"ThrottlingRateLimit": 5, "ThrottlingBurstLimit": 10},
        },
    )


def test_app_lambdas_use_python312_arm64(template: Template) -> None:
    for name in ("HealthFunction", "MeFunction", "DocumentsFunction"):
        fns = {k: v for k, v in template.find_resources("AWS::Lambda::Function").items() if name in k}
        assert len(fns) == 1, name
        props = next(iter(fns.values()))["Properties"]
        assert props["Runtime"] == "python3.12" and props["Architectures"] == ["arm64"]


def test_log_groups_have_short_retention(template: Template) -> None:
    template.all_resources_properties("AWS::Logs::LogGroup", {"RetentionInDays": 7})


def test_nothing_is_retained_after_destroy(template: Template) -> None:
    """D-002: `cdk destroy` must leave no billable leftovers."""
    for logical_id, res in template.to_json()["Resources"].items():
        assert res.get("DeletionPolicy") != "Retain", logical_id
        assert res.get("UpdateReplacePolicy") != "Retain", logical_id


def test_resources_are_tagged(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {"Tags": Match.array_with([{"Key": "Project", "Value": "CloudDocsAI"}])},
    )


def test_buckets_are_private_and_auto_deleted(template: Template) -> None:
    template.resource_count_is("AWS::S3::Bucket", 2)  # site + documents
    template.all_resources_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "Tags": Match.array_with([{"Key": "aws-cdk:auto-delete-objects", "Value": "true"}]),
        },
    )


def test_cloudfront_uses_oac_https_and_security_headers(template: Template) -> None:
    template.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    template.has_resource_properties(
        "AWS::CloudFront::Distribution",
        {
            "DistributionConfig": Match.object_like(
                {
                    "DefaultRootObject": "index.html",
                    "DefaultCacheBehavior": Match.object_like(
                        {"ViewerProtocolPolicy": "redirect-to-https"}
                    ),
                }
            )
        },
    )
    policy = next(iter(template.find_resources("AWS::CloudFront::ResponseHeadersPolicy").values()))
    sec = policy["Properties"]["ResponseHeadersPolicyConfig"]["SecurityHeadersConfig"]
    csp = sec["ContentSecurityPolicy"]["ContentSecurityPolicy"]
    assert "frame-ancestors 'none'" in csp and "script-src 'self'" in csp
    assert "https://cognito-idp.ap-southeast-1.amazonaws.com" in csp
    assert sec["FrameOptions"]["FrameOption"] == "DENY"


def test_api_cors_allows_only_configured_and_cloudfront_origins(template: Template) -> None:
    api = next(iter(template.find_resources("AWS::ApiGatewayV2::Api").values()))
    origins = api["Properties"]["CorsConfiguration"]["AllowOrigins"]
    assert len(origins) == 2 and "*" not in origins
    assert "http://localhost:5173" in origins
    assert any(isinstance(o, dict) for o in origins), "CloudFront domain (a CFN reference) must be allowed"


def test_site_deployment_writes_runtime_config(template: Template) -> None:
    template.resource_count_is("Custom::CDKBucketDeployment", 1)


# ---------------------------------------------------------------- Phase 2: documents


def _documents_fn(template: Template) -> tuple[str, dict]:
    fns = {k: v for k, v in template.find_resources("AWS::Lambda::Function").items() if "DocumentsFunction" in k}
    assert len(fns) == 1
    return next(iter(fns.items()))


def test_documents_table_is_on_demand_pk_sk_and_destroyable(template: Template) -> None:
    template.has_resource(
        "AWS::DynamoDB::Table",
        {
            "Properties": Match.object_like(
                {
                    "BillingMode": "PAY_PER_REQUEST",
                    "KeySchema": [
                        {"AttributeName": "PK", "KeyType": "HASH"},
                        {"AttributeName": "SK", "KeyType": "RANGE"},
                    ],
                }
            ),
            "DeletionPolicy": "Delete",
        },
    )


def test_documents_bucket_is_private_with_post_only_cors(template: Template) -> None:
    buckets = [
        v["Properties"] for k, v in template.find_resources("AWS::S3::Bucket").items() if "DocumentsBucket" in k
    ]
    assert len(buckets) == 1
    props = buckets[0]
    assert props["PublicAccessBlockConfiguration"]["RestrictPublicBuckets"] is True
    rules = props["CorsConfiguration"]["CorsRules"]
    assert len(rules) == 1 and rules[0]["AllowedMethods"] == ["POST"]
    assert "*" not in rules[0]["AllowedOrigins"] and "http://localhost:5173" in rules[0]["AllowedOrigins"]


def test_documents_routes_exist_and_require_jwt(template: Template) -> None:
    routes = {
        r["Properties"]["RouteKey"]: r["Properties"].get("AuthorizationType")
        for r in template.find_resources("AWS::ApiGatewayV2::Route").values()
    }
    for key in [
        "POST /documents/upload-url",
        "POST /documents/{id}/complete",
        "GET /documents",
        "GET /documents/{id}",
    ]:
        assert routes.get(key) == "JWT", key
    assert "DELETE /documents/{id}" not in routes  # wired in Phase 5


def test_documents_lambda_gets_table_and_bucket_from_env(template: Template) -> None:
    _, fn = _documents_fn(template)
    env = fn["Properties"]["Environment"]["Variables"]
    assert set(env) == {"DOCUMENTS_TABLE", "DOCUMENTS_BUCKET", "KNOWLEDGE_BASE_ID", "DATA_SOURCE_ID"}


def test_documents_lambda_iam_is_least_privilege(template: Template) -> None:
    name, fn = _documents_fn(template)
    role_ref = fn["Properties"]["Role"]["Fn::GetAtt"][0]
    policies = [
        p["Properties"]["PolicyDocument"]["Statement"]
        for p in template.find_resources("AWS::IAM::Policy").values()
        if {"Ref": role_ref} in p["Properties"]["Roles"]
    ]
    statements = [s for group in policies for s in group]
    actions = set()
    for st in statements:
        acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        actions.update(acts)
        assert st["Resource"] != "*", f"wildcard resource in {name}: {st}"
        assert not any(a.endswith(":*") for a in acts), f"wildcard action: {acts}"
    assert actions == {
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "bedrock:StartIngestionJob",
        "bedrock:IngestKnowledgeBaseDocuments",
        "bedrock:GetKnowledgeBaseDocuments",
        "bedrock:DeleteKnowledgeBaseDocuments",
    }
    listing = next(s for s in statements if s["Action"] == "s3:ListBucket")
    assert listing["Condition"] == {"StringLike": {"s3:prefix": ["uploads/*"]}}


def test_csp_allows_browser_upload_to_regional_s3(template: Template) -> None:
    policy = next(iter(template.find_resources("AWS::CloudFront::ResponseHeadersPolicy").values()))
    csp = policy["Properties"]["ResponseHeadersPolicyConfig"]["SecurityHeadersConfig"]["ContentSecurityPolicy"][
        "ContentSecurityPolicy"
    ]
    assert "https://*.s3.ap-southeast-1.amazonaws.com" in csp


# ---------------------------------------------------------------- Phase 3: Knowledge Base


def test_vector_index_matches_cohere_and_spike(template: Template) -> None:
    template.has_resource(
        "AWS::S3Vectors::Index",
        {
            "Properties": Match.object_like(
                {
                    "DataType": "float32",
                    "Dimension": 1024,
                    "DistanceMetric": "cosine",
                    "MetadataConfiguration": {
                        "NonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
                    },
                }
            ),
            "DeletionPolicy": "Delete",
        },
    )
    template.resource_count_is("AWS::S3Vectors::VectorBucket", 1)


def test_knowledge_base_uses_s3_vectors_and_cohere(template: Template) -> None:
    kb = next(iter(template.find_resources("AWS::Bedrock::KnowledgeBase").values()))
    props = kb["Properties"]
    assert props["StorageConfiguration"]["Type"] == "S3_VECTORS"
    model = props["KnowledgeBaseConfiguration"]["VectorKnowledgeBaseConfiguration"]["EmbeddingModelArn"]
    assert "cohere.embed-multilingual-v3" in str(model)
    assert kb.get("DeletionPolicy") == "Delete"


def test_data_source_is_uploads_prefix_fixed_chunks_and_deletes_vectors(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Bedrock::DataSource",
        {
            "DataDeletionPolicy": "DELETE",
            "DataSourceConfiguration": Match.object_like(
                {"Type": "S3", "S3Configuration": Match.object_like({"InclusionPrefixes": ["uploads/"]})}
            ),
            "VectorIngestionConfiguration": {
                "ChunkingConfiguration": {
                    "ChunkingStrategy": "FIXED_SIZE",
                    "FixedSizeChunkingConfiguration": {"MaxTokens": 300, "OverlapPercentage": 20},
                }
            },
        },
    )


def _role_statements(template: Template, role_logical_id: str) -> list[dict]:
    return [
        st
        for p in template.find_resources("AWS::IAM::Policy").values()
        if {"Ref": role_logical_id} in p["Properties"]["Roles"]
        for st in p["Properties"]["PolicyDocument"]["Statement"]
    ]


def test_knowledge_base_role_is_scoped(template: Template) -> None:
    roles = {k: v for k, v in template.find_resources("AWS::IAM::Role").items() if "KnowledgeBaseRole" in k}
    assert len(roles) == 1
    logical_id, role = next(iter(roles.items()))
    trust = role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    assert trust["Principal"] == {"Service": "bedrock.amazonaws.com"}
    assert "aws:SourceAccount" in trust["Condition"]["StringEquals"]
    assert "aws:SourceArn" in trust["Condition"]["ArnLike"]
    statements = _role_statements(template, logical_id)
    actions = set()
    for st in statements:
        acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        actions.update(acts)
        assert st["Resource"] != "*" and not any(a.endswith(":*") for a in acts), st
    assert actions == {
        "bedrock:InvokeModel",
        "s3:GetObject",
        "s3:ListBucket",
        "s3vectors:PutVectors",
        "s3vectors:GetVectors",
        "s3vectors:DeleteVectors",
        "s3vectors:QueryVectors",
        "s3vectors:GetIndex",
    }


def test_documents_lambda_can_only_manage_documents_in_this_kb(template: Template) -> None:
    _, fn = _documents_fn(template)
    env = fn["Properties"]["Environment"]["Variables"]
    assert {"KNOWLEDGE_BASE_ID", "DATA_SOURCE_ID"} <= set(env)
    statements = _role_statements(template, fn["Properties"]["Role"]["Fn::GetAtt"][0])
    bedrock = [st for st in statements if any(str(a).startswith("bedrock:") for a in st["Action"])]
    assert len(bedrock) == 1
    assert sorted(bedrock[0]["Action"]) == [
        "bedrock:DeleteKnowledgeBaseDocuments",
        "bedrock:GetKnowledgeBaseDocuments",
        "bedrock:IngestKnowledgeBaseDocuments",
        "bedrock:StartIngestionJob",
    ]
    assert "KnowledgeBase" in str(bedrock[0]["Resource"])  # the KB's ARN, not "*"


def test_initial_sync_runs_once_at_deploy(template: Template) -> None:
    sync = [v for k, v in template.find_resources("Custom::AWS").items() if "InitialSync" in k]
    assert len(sync) == 1
    assert "StartIngestionJob" in json.dumps(sync[0]["Properties"]["Create"])
