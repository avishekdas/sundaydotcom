"""Bootstrap admin custom resource (K7.6, A1.1, D-055): built for every stage that configures an admin email."""

from __future__ import annotations

import dataclasses

import aws_cdk as cdk
from aws_cdk.assertions import Match

from tasklane_infra.app_builder import build
from tasklane_infra.config import DEV
from tests.conftest import template


def test_dev_bootstraps_the_configured_admin(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-bootstrap")
    t.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Handler": "tasklane.workers.bootstrap.handler",
            "Environment": {"Variables": Match.object_like({"ADMIN_EMAIL": "avishekdas.cool@gmail.com"})},
        },
    )
    assert t.find_resources("Custom::Bootstrap")
    actions: set[str] = set()
    for pol in t.find_resources("AWS::IAM::Policy").values():
        for st in pol["Properties"]["PolicyDocument"]["Statement"]:
            a = st["Action"]
            for x in a if isinstance(a, list) else [a]:
                if x.startswith("cognito-idp:"):
                    actions.add(x)
                    assert st["Resource"] != "*"
    assert actions == {"cognito-idp:AdminCreateUser", "cognito-idp:AdminGetUser"}


def test_no_bootstrap_without_an_email() -> None:
    a = cdk.App()
    build(a, dataclasses.replace(DEV, bootstrap_admin_email=None))
    assert not any(isinstance(s, cdk.Stack) and s.stack_name.endswith("-bootstrap") for s in a.node.children)
