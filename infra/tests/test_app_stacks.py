"""Identity, Api, Realtime and Edge stacks (arch 02): skeleton wiring for the M0b walking skeleton."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from tests.conftest import template


def test_user_pool_is_admin_invite_only_with_strong_passwords(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-identity")
    t.has_resource_properties(
        "AWS::Cognito::UserPool",
        {
            "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
            "Policies": {"PasswordPolicy": Match.object_like({"MinimumLength": 12})},
            "UsernameAttributes": ["email"],
        },
    )
    t.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {"GenerateSecret": False, "ExplicitAuthFlows": Match.array_with(["ALLOW_USER_PASSWORD_AUTH"])},
    )


def test_http_api_has_jwt_authorizer_and_api_lambda(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-api")
    t.has_resource_properties("AWS::ApiGatewayV2::Authorizer", {"AuthorizerType": "JWT"})
    t.has_resource_properties("AWS::ApiGatewayV2::Api", {"ProtocolType": "HTTP"})
    t.has_resource_properties(
        "AWS::Lambda::Function", {"FunctionName": "tasklane-dev-api", "Handler": "tasklane.api.app.handler"}
    )
    routes = [r["Properties"] for r in t.find_resources("AWS::ApiGatewayV2::Route").values()]
    assert routes and all(r.get("AuthorizationType") == "JWT" for r in routes)


def test_api_uses_api_rw_secret_and_can_put_events(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-api")
    fn = next(
        f
        for f in t.find_resources("AWS::Lambda::Function").values()
        if f["Properties"].get("FunctionName") == "tasklane-dev-api"
    )
    assert "tlapirw" in str(fn["Properties"]["Environment"]["Variables"]["DB_SECRET_ARN"]).replace("_", "")
    t.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with([Match.object_like({"Action": "events:PutEvents"})])
            }
        },
    )


def test_websocket_api_routes_and_ttl_table(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-realtime")
    t.has_resource_properties("AWS::ApiGatewayV2::Api", {"ProtocolType": "WEBSOCKET"})
    keys = {r["Properties"]["RouteKey"] for r in t.find_resources("AWS::ApiGatewayV2::Route").values()}
    assert keys == {"$connect", "$disconnect", "$default"}
    t.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
            "BillingMode": "PAY_PER_REQUEST",
        },
    )
    t.has_resource_properties(
        "AWS::Events::Rule", {"EventPattern": {"source": ["tasklane"], "detail-type": [{"prefix": "item."}]}}
    )


def test_edge_serves_spa_api_and_ws_from_one_distribution(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-edge")
    dist = next(iter(t.find_resources("AWS::CloudFront::Distribution").values()))["Properties"][
        "DistributionConfig"
    ]
    paths = {b["PathPattern"] for b in dist["CacheBehaviors"]}
    assert {"/api/*", "/ws"} <= paths
    t.has_resource_properties(
        "AWS::S3::Bucket", {"PublicAccessBlockConfiguration": Match.object_like({"BlockPublicAcls": True})}
    )


def test_api_deploys_through_a_canary_with_automatic_rollback(app: cdk.App) -> None:  # PE-6
    t = template(app, "tasklane-dev-api")
    t.has_resource_properties("AWS::Lambda::Alias", {"Name": "live"})
    t.has_resource_properties(
        "AWS::CodeDeploy::DeploymentGroup",
        {
            "DeploymentConfigName": "CodeDeployDefault.LambdaCanary10Percent5Minutes",
            "AutoRollbackConfiguration": {
                "Enabled": True,
                "Events": Match.array_with(["DEPLOYMENT_FAILURE", "DEPLOYMENT_STOP_ON_ALARM"]),
            },
            "AlarmConfiguration": Match.object_like({"Enabled": True}),
        },
    )
    integ = next(iter(t.find_resources("AWS::ApiGatewayV2::Integration").values()))["Properties"]
    alias_ids = set(t.find_resources("AWS::Lambda::Alias"))
    assert integ["IntegrationUri"] in [{"Ref": a} for a in alias_ids]


def test_test_hooks_are_never_enabled_in_prod() -> (
    None
):  # plan M0b-8: fake clock / fault injection absent from prod
    import dataclasses

    import pytest

    from tasklane_infra.app_builder import build
    from tasklane_infra.config import DEV

    with pytest.raises(ValueError, match="test hooks"):
        build(cdk.App(), dataclasses.replace(DEV, name="prod", test_hooks=True))
    a = cdk.App()
    build(a, dataclasses.replace(DEV, name="prod", test_hooks=False, account="123456789012"))
    for s in a.node.children:
        if isinstance(s, cdk.Stack):
            for fn in Template.from_stack(s).find_resources("AWS::Lambda::Function").values():
                env = fn["Properties"].get("Environment", {}).get("Variables", {})
                assert not {"TL_FAULT_INJECTION", "TL_FAKE_CLOCK"} & set(env)
                assert env.get("STAGE", "prod") == "prod"
