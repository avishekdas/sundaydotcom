"""Builds every stack for a stage. Stack names: tasklane-<stage>-<name>."""

from __future__ import annotations

import aws_cdk as cdk

from tasklane_infra.config import Stage
from tasklane_infra.stacks.api import ApiStack
from tasklane_infra.stacks.bootstrap import BootstrapStack
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.edge import EdgeStack
from tasklane_infra.stacks.identity import IdentityStack
from tasklane_infra.stacks.messaging import MessagingStack
from tasklane_infra.stacks.migrate import MigrateStack
from tasklane_infra.stacks.network import NetworkStack
from tasklane_infra.stacks.observability import ObservabilityStack
from tasklane_infra.stacks.realtime import RealtimeStack
from tasklane_infra.stacks.test_identities import TestIdentitiesStack
from tasklane_infra.stacks.workers import WorkersStack


def build(app: cdk.App, stage: Stage) -> None:
    if stage.name == "prod" and stage.test_hooks:
        raise ValueError("test hooks (fake clock, fault injection) must never be enabled in prod")
    env = cdk.Environment(account=stage.account, region=stage.region)
    name = lambda s: f"tasklane-{stage.name}-{s}"  # noqa: E731
    net = NetworkStack(app, name("network"), stack_name=name("network"), env=env)
    data = DataStack(
        app,
        name("data"),
        stack_name=name("data"),
        env=env,
        stage=stage,
        vpc=net.vpc,
        termination_protection=True,
    )
    mig = MigrateStack(app, name("migrate"), stack_name=name("migrate"), env=env, stage=stage, data=data)
    msg = MessagingStack(app, name("messaging"), stack_name=name("messaging"), env=env, stage=stage)
    wrk = WorkersStack(
        app, name("workers"), stack_name=name("workers"), env=env, stage=stage, data=data, messaging=msg
    )
    wrk.add_dependency(mig)  # code stacks deploy after the migrate stack (the pipeline migrates in between)
    idn = IdentityStack(app, name("identity"), stack_name=name("identity"), env=env, stage=stage)
    rt = RealtimeStack(
        app, name("realtime"), stack_name=name("realtime"), env=env, stage=stage, data=data, messaging=msg
    )
    api = ApiStack(
        app,
        name("api"),
        stack_name=name("api"),
        env=env,
        stage=stage,
        data=data,
        identity=idn,
        messaging=msg,
        realtime=rt,
    )
    edge = EdgeStack(
        app, name("edge"), stack_name=name("edge"), env=env, stage=stage, api=api, realtime=rt, identity=idn
    )
    obs = ObservabilityStack(
        app,
        name("observability"),
        stack_name=name("observability"),
        env=env,
        stage=stage,
        data=data,
        messaging=msg,
        workers=wrk,
        api=api,
        realtime=rt,
    )
    for code in (rt, api):
        code.add_dependency(mig)
    stacks: list[cdk.Stack] = [net, data, mig, msg, wrk, idn, rt, api, edge, obs]
    if stage.bootstrap_admin_email:  # K7.6: first Admin from config (D-055)
        boot = BootstrapStack(
            app,
            name("bootstrap"),
            stack_name=name("bootstrap"),
            env=env,
            stage=stage,
            data=data,
            identity=idn,
        )
        boot.add_dependency(mig)
        stacks.append(boot)
    if stage.test_hooks:  # dev-only fixtures (D-049); build() already refuses test hooks for prod
        tid = TestIdentitiesStack(
            app,
            name("test-identities"),
            stack_name=name("test-identities"),
            env=env,
            stage=stage,
            data=data,
            identity=idn,
            counters=api.counters,
            base_url=f"https://{edge.distribution.distribution_domain_name}",
        )
        tid.add_dependency(mig)  # tl.users must exist (the pipeline migrates before code stacks)
        stacks.append(tid)
    for s in stacks:
        cdk.Tags.of(s).add("project", "tasklane")
        cdk.Tags.of(s).add("stage", stage.name)
