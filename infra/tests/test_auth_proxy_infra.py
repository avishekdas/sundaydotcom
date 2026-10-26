"""Auth proxy wiring (ADR-013, arch 07 §7.1/§7.4, D-048, D-050…D-052)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match

from tests.conftest import template


def test_proxy_client_uses_admin_auth_30_day_refresh_and_revocation(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-identity")
    t.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {
            "ClientName": "tasklane-dev-proxy",
            "GenerateSecret": False,
            "ExplicitAuthFlows": Match.array_with(
                ["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
            ),
            "EnableTokenRevocation": True,
            "PreventUserExistenceErrors": "ENABLED",
            "RefreshTokenValidity": 43200,  # minutes = 30 days (D-048)
            "TokenValidityUnits": Match.object_like({"RefreshToken": "minutes"}),
        },
    )


def test_origin_secret_parameter_is_generated_once(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-identity")
    assert t.find_resources("Custom::OriginSecret")
    stmts = [
        st
        for pol in t.find_resources("AWS::IAM::Policy").values()
        for st in pol["Properties"]["PolicyDocument"]["Statement"]
    ]
    put = [
        st
        for st in stmts
        if "ssm:PutParameter" in (st["Action"] if isinstance(st["Action"], list) else [st["Action"]])
    ]
    assert put and all(st["Resource"] != "*" for st in put)


def test_auth_routes_skip_the_jwt_authorizer(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-api")
    t.has_resource_properties(
        "AWS::ApiGatewayV2::Route",
        {"RouteKey": "ANY /api/auth/{proxy+}", "AuthorizationType": "NONE"},
    )


def _api_fn(t):  # type: ignore[no-untyped-def]
    return next(
        r
        for r in t.find_resources("AWS::Lambda::Function").values()
        if r["Properties"].get("FunctionName") == "tasklane-dev-api"
    )


def test_api_lambda_gets_proxy_env_and_only_the_cognito_actions_it_uses(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-api")
    env = _api_fn(t)["Properties"]["Environment"]["Variables"]
    for k in ("USER_POOL_ID", "COGNITO_CLIENT_ID", "COUNTERS_TABLE", "ORIGIN_SECRET"):
        assert k in env
    actions: set[str] = set()
    for pol in t.find_resources("AWS::IAM::Policy").values():
        for st in pol["Properties"]["PolicyDocument"]["Statement"]:
            a = st["Action"]
            for x in a if isinstance(a, list) else [a]:
                if x.startswith("cognito-idp:"):
                    actions.add(x)
                    assert st["Resource"] != "*"
    assert actions == {"cognito-idp:AdminInitiateAuth", "cognito-idp:AdminUserGlobalSignOut"}  # D-051


def test_counters_table_is_on_demand_with_ttl(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-api")
    t.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "BillingMode": "PAY_PER_REQUEST",
            "TimeToLiveSpecification": {"AttributeName": "expires_at", "Enabled": True},
            "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
        },
    )


def test_account_closed_raises_a_sev2_alarm(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-api")
    t.has_resource_properties(
        "AWS::Logs::MetricFilter", {"FilterPattern": Match.string_like_regexp("auth.account_closed")}
    )
    alarms = t.find_resources("AWS::CloudWatch::Alarm")
    closed = [a for a in alarms.values() if "AccountClosed" in a["Properties"].get("MetricName", "")]
    assert closed and closed[0]["Properties"].get("AlarmActions")
    assert "runbook" in closed[0]["Properties"].get("AlarmDescription", "").lower()


def test_cloudfront_sends_the_origin_secret_to_the_api(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-edge")
    cfg = next(iter(t.find_resources("AWS::CloudFront::Distribution").values()))["Properties"][
        "DistributionConfig"
    ]
    api_origin = next(b["TargetOriginId"] for b in cfg["CacheBehaviors"] if b["PathPattern"] == "/api/*")
    origin = next(o for o in cfg["Origins"] if o["Id"] == api_origin)
    headers = {h["HeaderName"]: h["HeaderValue"] for h in origin.get("OriginCustomHeaders", [])}
    assert "x-tl-origin" in headers and "resolve:ssm:" in str(headers["x-tl-origin"])
