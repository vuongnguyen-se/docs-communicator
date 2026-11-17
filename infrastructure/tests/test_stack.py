"""Synth-time checks of security and teardown rules. No AWS credentials needed."""

from __future__ import annotations

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
    for name in ("HealthFunction", "MeFunction"):
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


def test_site_bucket_is_private_and_auto_deleted(template: Template) -> None:
    template.has_resource_properties(
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
