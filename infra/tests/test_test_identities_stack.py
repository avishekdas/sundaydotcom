"""Scripted dev test identities (PE-17, M0B-24, D-049): a dev-only custom resource, never built for prod."""

from __future__ import annotations

import dataclasses

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match

from tasklane_infra.app_builder import build
from tasklane_infra.config import DEV
from tests.conftest import template


def test_dev_has_test_identities_custom_resource(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-test-identities")
    t.has_resource_properties("AWS::SecretsManager::Secret", {"Name": "tasklane/dev/test-users/all"})
    t.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "tasklane.workers.test_identities.handler",
            "Environment": {"Variables": Match.object_like({"STAGE": "dev", "SECRET_ID": Match.any_value()})},
        },
    )
    assert t.find_resources("AWS::CloudFormation::CustomResource") or t.find_resources(
        "Custom::TestIdentities"
    )


def test_identity_lambda_may_only_admin_the_pool(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-test-identities")
    actions: set[str] = set()
    for pol in t.find_resources("AWS::IAM::Policy").values():
        for st in pol["Properties"]["PolicyDocument"]["Statement"]:
            a = st["Action"]
            for x in a if isinstance(a, list) else [a]:
                if x.startswith("cognito-idp:"):
                    actions.add(x)
                    assert st["Resource"] != "*"
    assert {
        "cognito-idp:AdminCreateUser",
        "cognito-idp:AdminSetUserPassword",
        "cognito-idp:AdminGetUser",
    } <= actions


@pytest.mark.parametrize(
    "stage",
    [
        dataclasses.replace(DEV, name="prod", test_hooks=False),
        dataclasses.replace(DEV, name="qa", test_hooks=False),
    ],
)
def test_no_test_identities_without_test_hooks(stage: object) -> None:
    a = cdk.App()
    build(a, stage)  # type: ignore[arg-type]
    names = [s.stack_name for s in a.node.children if isinstance(s, cdk.Stack)]
    assert not any(n.endswith("-test-identities") for n in names)


def test_ip_probe_is_a_dev_only_test_hook(app: cdk.App) -> None:
    """AC-K7-2 two-IP check (D-046): λ in the test-identities stack, DynamoDB rights on the counters table only."""
    t = template(app, "tasklane-dev-test-identities")
    t.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": "tasklane-dev-ip-probe", "Handler": "tasklane.workers.ip_probe.handler",
         "Environment": {"Variables": Match.object_like({"STAGE": "dev", "BASE_URL": Match.any_value(),
                                                          "COUNTERS_TABLE": Match.any_value()})}},
    )
    ddb = set()
    for pol in t.find_resources("AWS::IAM::Policy").values():
        for st in pol["Properties"]["PolicyDocument"]["Statement"]:
            a = st["Action"]
            for x in a if isinstance(a, list) else [a]:
                if x.startswith("dynamodb:"):
                    ddb.add(x)
                    assert st["Resource"] != "*"
    assert ddb == {"dynamodb:Scan", "dynamodb:DeleteItem"}
