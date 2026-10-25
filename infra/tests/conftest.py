from __future__ import annotations

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from tasklane_infra.app_builder import build
from tasklane_infra.config import DEV


@pytest.fixture(scope="session")
def app() -> cdk.App:
    a = cdk.App()
    build(a, DEV)
    return a


def template(app: cdk.App, name: str) -> Template:
    stack = next(s for s in app.node.children if isinstance(s, cdk.Stack) and s.stack_name == name)
    return Template.from_stack(stack)
