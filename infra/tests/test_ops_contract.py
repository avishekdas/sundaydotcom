"""Operational contract (PE-7, M0B-6/16/17): every running function has an errors alarm and a dashboard panel,
every DLQ is on the dashboard, every rule target retries into a DLQ, schedule-fed alarms can fire at their data
cadence, every alarm's runbook exists, and the api canary is gated by a pre-traffic smoke test."""

from __future__ import annotations

import json
from pathlib import Path

import aws_cdk as cdk

from tests.conftest import template

ALL = [
    "tasklane-dev-messaging",
    "tasklane-dev-workers",
    "tasklane-dev-realtime",
    "tasklane-dev-api",
    "tasklane-dev-edge",
    "tasklane-dev-identity",
    "tasklane-dev-observability",
]
# one-shot pipeline / deploy-time functions: their failures fail the deploy itself
NOT_RUNTIME = ("-migrate", "-test-identities", "-bootstrap", "-predeploy-hook")
RUNBOOKS = Path(__file__).resolve().parents[2] / "ops" / "runbooks"
SCHEDULE_INTERVAL_S = 3600  # dev: hourly (D-037)


def _resources(app: cdk.App, rtype: str) -> dict[str, dict]:  # type: ignore[type-arg]
    out: dict[str, dict] = {}  # type: ignore[type-arg]
    for s in ALL:
        out.update(template(app, s).find_resources(rtype))
    return out


def _runtime_functions(app: cdk.App) -> dict[str, str]:
    fns = {}
    for logical, fn in _resources(app, "AWS::Lambda::Function").items():
        name = fn["Properties"].get("FunctionName")
        if isinstance(name, str) and name.startswith("tasklane-dev-") and not name.endswith(NOT_RUNTIME):
            fns[logical] = name
    return fns


def test_runtime_functions_are_the_expected_set(app: cdk.App) -> None:
    names = set(_runtime_functions(app).values())
    assert {
        "tasklane-dev-api",
        "tasklane-dev-fanout",
        "tasklane-dev-ws-handlers",
        "tasklane-dev-outbox-acker",
        "tasklane-dev-outbox-sweeper",
        "tasklane-dev-scheduler-tick",
    } <= names


def test_every_runtime_function_has_an_errors_alarm(app: cdk.App) -> None:
    alarms = [a["Properties"] for a in _resources(app, "AWS::CloudWatch::Alarm").values()]
    for logical, name in _runtime_functions(app).items():
        assert any(
            a.get("MetricName") == "Errors" and logical in json.dumps(a.get("Dimensions", [])) for a in alarms
        ), f"no Errors alarm for {name}"


def test_every_runtime_function_and_dlq_is_on_the_dashboard(app: cdk.App) -> None:
    dash = json.dumps(
        template(app, "tasklane-dev-observability").find_resources("AWS::CloudWatch::Dashboard")
    )
    for logical, name in _runtime_functions(app).items():
        assert logical in dash, f"{name} has no dashboard panel"
    dlqs = [
        k
        for k, v in _resources(app, "AWS::SQS::Queue").items()
        if str(v["Properties"].get("QueueName", "")).endswith("-dlq")
    ]
    assert dlqs
    for dlq in dlqs:
        assert dlq in dash, f"{dlq} depth is not on the dashboard"


def test_every_rule_target_retries_into_a_dlq(app: cdk.App) -> None:
    rules = _resources(app, "AWS::Events::Rule")
    assert rules
    for name, r in rules.items():
        for t in r["Properties"].get("Targets", []):
            assert "DeadLetterConfig" in t and "RetryPolicy" in t, f"{name} target {t.get('Id')}"


def test_schedule_fed_alarms_can_fire_at_the_schedule_cadence(app: cdk.App) -> None:
    alarms = template(app, "tasklane-dev-workers").find_resources("AWS::CloudWatch::Alarm")
    fed = [a["Properties"] for a in alarms.values() if a["Properties"].get("Namespace") == "Tasklane/Outbox"]
    assert fed
    for a in fed:
        window = a["Period"] * a.get("DatapointsToAlarm", a["EvaluationPeriods"])
        assert window >= SCHEDULE_INTERVAL_S, f"{a.get('AlarmName')} needs {window}s ≥ {SCHEDULE_INTERVAL_S}s"


def test_every_alarm_runbook_exists(app: cdk.App) -> None:
    prefix = "runbook: https://github.com/avishekdas/sundaydotcom/blob/main/ops/runbooks/"
    for name, a in _resources(app, "AWS::CloudWatch::Alarm").items():
        desc = json.dumps(a["Properties"]["AlarmDescription"])
        assert prefix in desc, name
        file = desc.split(prefix, 1)[1].split(".md", 1)[0] + ".md"
        assert (RUNBOOKS / file).is_file(), f"{name} links missing runbook {file}"


def test_canary_alarm_links_the_bad_deploy_runbook(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-api")
    live = [
        a for a in t.find_resources("AWS::CloudWatch::Alarm").values() if "live alias" in str(a["Properties"])
    ]
    assert live and "bad-deploy.md" in json.dumps(live[0]["Properties"]["AlarmDescription"])


def test_api_canary_runs_a_pre_traffic_smoke_test(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-api")
    alias = next(iter(t.find_resources("AWS::Lambda::Alias").values()))
    hook = alias["UpdatePolicy"]["CodeDeployLambdaAliasUpdate"].get("BeforeAllowTrafficHook")
    assert hook, "no BeforeAllowTrafficHook on the live alias"
    fns = t.find_resources("AWS::Lambda::Function")
    hook_fn = next(
        v for v in fns.values() if v["Properties"].get("FunctionName") == "tasklane-dev-predeploy-hook"
    )
    env = hook_fn["Properties"]["Environment"]["Variables"]
    assert {"TARGET_VERSION_ARN", "ORIGIN_SECRET"} <= set(env)
    assert hook_fn["Properties"]["Handler"] == "tasklane.workers.predeploy_hook.handler"


def test_alias_update_waits_for_the_codedeploy_role_policy(app: cdk.App) -> None:
    """866ac9f deploy: the alias update started the CodeDeploy deployment while the policy letting CodeDeploy invoke
    the pre-traffic hook was still being created → "Internal error occurred" and a rollback."""
    t = template(app, "tasklane-dev-api")
    alias = next(iter(t.find_resources("AWS::Lambda::Alias").values()))
    policies = [
        k for k in t.find_resources("AWS::IAM::Policy") if k.startswith("CanaryServiceRoleDefaultPolicy")
    ]
    assert policies and set(policies) <= set(alias.get("DependsOn", []))
