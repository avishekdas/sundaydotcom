"""Builds every stack for a stage. Stack names: tasklane-<stage>-<name>."""

from __future__ import annotations

import aws_cdk as cdk

from tasklane_infra.config import Stage
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.network import NetworkStack


def build(app: cdk.App, stage: Stage) -> None:
    env = cdk.Environment(account=stage.account, region=stage.region)
    name = lambda s: f"tasklane-{stage.name}-{s}"  # noqa: E731
    net = NetworkStack(app, name("network"), stack_name=name("network"), env=env)
    data = DataStack(app, name("data"), stack_name=name("data"), env=env, stage=stage, vpc=net.vpc)
    for s in (net, data):
        cdk.Tags.of(s).add("project", "tasklane")
        cdk.Tags.of(s).add("stage", stage.name)
