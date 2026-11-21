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
    for name in ("HealthFunction", "MeFunction", "DocumentsFunction", "ChatFunction", "WorkerFunction"):
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
        "DELETE /documents/{id}",
    ]:
        assert routes.get(key) == "JWT", key


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


# ---------------------------------------------------------------- Phase 4: chat


def _fn(template: Template, name: str) -> dict:
    fns = [v for k, v in template.find_resources("AWS::Lambda::Function").items() if name in k]
    assert len(fns) == 1, name
    return fns[0]


def test_chat_route_requires_jwt(template: Template) -> None:
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Route", {"RouteKey": "POST /chat/query", "AuthorizationType": "JWT"}
    )


def test_chat_lambda_config(template: Template) -> None:
    fn = _fn(template, "ChatFunction")["Properties"]
    assert fn["Timeout"] == 29  # under API Gateway's 30 s integration limit
    env = fn["Environment"]["Variables"]
    assert {"KNOWLEDGE_BASE_ID", "MODEL_ARN", "DOCUMENTS_TABLE"} <= set(env)
    assert "inference-profile/apac.amazon.nova-lite-v1:0" in json.dumps(env["MODEL_ARN"])


def test_chat_iam_is_kb_scoped_and_one_model(template: Template) -> None:
    fn = _fn(template, "ChatFunction")
    statements = _role_statements(template, fn["Properties"]["Role"]["Fn::GetAtt"][0])
    by_action = {}
    for st in statements:
        acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        assert st["Resource"] != "*" and not any(a.endswith(":*") for a in acts), st
        for a in acts:
            by_action[a] = json.dumps(st["Resource"])
    assert set(by_action) == {
        "dynamodb:GetItem",
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate",
        "bedrock:InvokeModel",
        "bedrock:GetInferenceProfile",
    }
    assert "inference-profile/apac.amazon.nova-lite-v1:0" in by_action["bedrock:GetInferenceProfile"]
    assert "KnowledgeBase" in by_action["bedrock:RetrieveAndGenerate"]
    assert "foundation-model/amazon.nova-lite-v1:0" in by_action["bedrock:InvokeModel"]
    assert "inference-profile/apac.amazon.nova-lite-v1:0" in by_action["bedrock:InvokeModel"]


# ---------------------------------------------------------------- Phase 5: alarms


def test_alarms_cover_every_function_api_and_chat_latency(template: Template) -> None:
    alarms = template.find_resources("AWS::CloudWatch::Alarm")
    names = {k for k in alarms}
    for expected in ("HealthErrors", "MeErrors", "DocumentsErrors", "ChatErrors", "WorkerErrors", "Api5xx", "Api4xxSpike", "ChatSlow", "IngestDLQNotEmpty"):
        assert any(expected in n for n in names), expected
    for a in alarms.values():
        props = a["Properties"]
        assert props["TreatMissingData"] == "notBreaching"
        assert len(props["AlarmActions"]) == 1  # the SNS topic


def test_no_email_is_subscribed_unless_given_at_deploy(template: Template) -> None:
    template.resource_count_is("AWS::SNS::Topic", 1)
    template.resource_count_is("AWS::SNS::Subscription", 0)


def test_alarm_email_comes_from_deploy_context_only() -> None:
    app = cdk.App(context={"aws:cdk:bundling-stacks": [], "alarmEmail": "ops@example.com"})
    from stacks.config import load_config

    config = load_config(app)
    stack = CloudDocsStack(app, "WithEmail", config=config, env=cdk.Environment(account="111111111111", region="ap-southeast-1"))
    Template.from_stack(stack).has_resource_properties(
        "AWS::SNS::Subscription", {"Protocol": "email", "Endpoint": "ops@example.com"}
    )


# ---------------------------------------------------------------- Event-driven ingestion


def _queues(template: Template) -> tuple[dict, dict]:
    queues = template.find_resources("AWS::SQS::Queue")
    main = [v for k, v in queues.items() if "IngestQueue" in k]
    dlq = [v for k, v in queues.items() if "IngestDLQ" in k]
    assert len(main) == 1 and len(dlq) == 1
    return main[0], dlq[0]


def test_ingest_queues_are_encrypted_tls_only_and_destroyable(template: Template) -> None:
    main, dlq = _queues(template)
    for q in (main, dlq):
        assert q["Properties"]["SqsManagedSseEnabled"] is True
        assert q["DeletionPolicy"] == "Delete"
    tls = [
        s
        for p in template.find_resources("AWS::SQS::QueuePolicy").values()
        for s in p["Properties"]["PolicyDocument"]["Statement"]
        if s["Effect"] == "Deny" and s.get("Condition") == {"Bool": {"aws:SecureTransport": "false"}}
    ]
    assert len(tls) >= 2  # one per queue


def test_failed_messages_go_to_the_dlq_after_three_tries(template: Template) -> None:
    main, _ = _queues(template)
    props = main["Properties"]
    assert props["RedrivePolicy"]["maxReceiveCount"] == 3
    assert "IngestDLQ" in json.dumps(props["RedrivePolicy"]["deadLetterTargetArn"])
    assert props["VisibilityTimeout"] == 180  # 6 x the worker's 30 s timeout
    assert _fn(template, "WorkerFunction")["Properties"]["Timeout"] == 30


def test_s3_reports_only_uploaded_pdfs_to_the_queue(template: Template) -> None:
    (notif,) = template.find_resources("Custom::S3BucketNotifications").values()
    configs = notif["Properties"]["NotificationConfiguration"]["QueueConfigurations"]
    assert len(configs) == 1
    cfg = configs[0]
    assert cfg["Events"] == ["s3:ObjectCreated:*"]
    rules = {r["Name"]: r["Value"] for r in cfg["Filter"]["Key"]["FilterRules"]}
    assert rules == {"prefix": "uploads/", "suffix": ".pdf"}  # sidecars (.pdf.metadata.json) excluded
    assert "IngestQueue" in json.dumps(cfg["QueueArn"])


def test_worker_reads_the_queue_in_small_batches_with_partial_retries(template: Template) -> None:
    (mapping,) = template.find_resources("AWS::Lambda::EventSourceMapping").values()
    props = mapping["Properties"]
    assert props["BatchSize"] == 5
    assert props["FunctionResponseTypes"] == ["ReportBatchItemFailures"]
    assert props["ScalingConfig"] == {"MaximumConcurrency": 2}
    assert "IngestQueue" in json.dumps(props["EventSourceArn"])
    assert "WorkerFunction" in json.dumps(props["FunctionName"])


def test_worker_iam_is_a_strict_subset_for_verify_and_ingest(template: Template) -> None:
    fn = _fn(template, "WorkerFunction")
    statements = _role_statements(template, fn["Properties"]["Role"]["Fn::GetAtt"][0])
    by_action: dict[str, str] = {}
    for st in statements:
        acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        assert st["Resource"] != "*" and not any(a.endswith(":*") for a in acts), st
        for a in acts:
            by_action[a] = json.dumps(st["Resource"])
    assert set(by_action) == {
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:PutObject",
        "s3:ListBucket",
        "bedrock:StartIngestionJob",
        "bedrock:IngestKnowledgeBaseDocuments",
        # Added by the SQS event source, on the ingest queue only:
        "sqs:ReceiveMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueUrl",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
    }
    assert '/uploads/*.pdf"' in by_action["s3:GetObject"]
    assert "/uploads/*.pdf.metadata.json" in by_action["s3:PutObject"]
    assert "KnowledgeBase" in by_action["bedrock:IngestKnowledgeBaseDocuments"]
    assert "IngestQueue" in by_action["sqs:ReceiveMessage"]


def test_worker_gets_resource_names_from_env(template: Template) -> None:
    env = _fn(template, "WorkerFunction")["Properties"]["Environment"]["Variables"]
    assert set(env) == {"DOCUMENTS_TABLE", "DOCUMENTS_BUCKET", "KNOWLEDGE_BASE_ID", "DATA_SOURCE_ID"}
