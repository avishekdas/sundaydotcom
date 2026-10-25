"""Builds every stack for a stage. Stack names: tasklane-<stage>-<name>."""

from __future__ import annotations

import aws_cdk as cdk

from tasklane_infra.config import Stage
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.messaging import MessagingStack
from tasklane_infra.stacks.migrate import MigrateStack
from tasklane_infra.stacks.network import NetworkStack
from tasklane_infra.stacks.workers import WorkersStack


def build(app: cdk.App, stage: Stage) -> None:
    env = cdk.Environment(account=stage.account, region=stage.region)
    name = lambda s: f"tasklane-{stage.name}-{s}"  # noqa: E731
    net = NetworkStack(app, name("network"), stack_name=name("network"), env=env)
    data = DataStack(app, name("data"), stack_name=name("data"), env=env, stage=stage, vpc=net.vpc)
    mig = MigrateStack(app, name("migrate"), stack_name=name("migrate"), env=env, stage=stage, data=data)
    msg = MessagingStack(app, name("messaging"), stack_name=name("messaging"), env=env, stage=stage)
    wrk = WorkersStack(
        app, name("workers"), stack_name=name("workers"), env=env, stage=stage, data=data, messaging=msg
    )
    wrk.add_dependency(mig)  # code stacks deploy after the migrate stack (the pipeline migrates in between)
    for s in (net, data, mig, msg, wrk):
        cdk.Tags.of(s).add("project", "tasklane")
        cdk.Tags.of(s).add("stage", stage.name)
