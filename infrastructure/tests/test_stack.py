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


def test_cors_allows_only_configured_origins(template: Template) -> None:
    template.has_resource_properties(
        "AWS::ApiGatewayV2::Api",
        {"CorsConfiguration": Match.object_like({"AllowOrigins": ["http://localhost:5173"]})},
    )


def test_lambdas_use_python312_arm64(template: Template) -> None:
    template.resource_count_is("AWS::Lambda::Function", 2)
    template.all_resources_properties(
        "AWS::Lambda::Function", {"Runtime": "python3.12", "Architectures": ["arm64"]}
    )


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
