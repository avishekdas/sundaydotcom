"""Delivery contract (PE-7, OPS-4): every queue has a DLQ + alarm, every schedule retries into a DLQ,
every alarm links a runbook; workers run as table-scoped DB roles, singletons are concurrency 1."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match

from tests.conftest import template

STACKS = ["tasklane-dev-messaging", "tasklane-dev-workers", "tasklane-dev-realtime", "tasklane-dev-api"]


def all_resources(app: cdk.App, rtype: str) -> dict[str, dict]:  # type: ignore[type-arg]
    out: dict[str, dict] = {}  # type: ignore[type-arg]
    for s in STACKS:
        out.update(template(app, s).find_resources(rtype))
    return out


def test_every_work_queue_has_a_dlq(app: cdk.App) -> None:
    queues = all_resources(app, "AWS::SQS::Queue")
    work = {k: v for k, v in queues.items() if not v["Properties"].get("QueueName", "").endswith("-dlq")}
    assert work, "expected at least one work queue"
    for name, q in work.items():
        assert "RedrivePolicy" in q["Properties"], f"{name} has no DLQ"


def test_every_dlq_has_a_depth_alarm(app: cdk.App) -> None:
    dlqs = [
        k
        for k, v in all_resources(app, "AWS::SQS::Queue").items()
        if v["Properties"].get("QueueName", "").endswith("-dlq")
    ]
    alarms = [
        str(a["Properties"].get("Dimensions")) for a in all_resources(app, "AWS::CloudWatch::Alarm").values()
    ]
    assert dlqs
    for dlq in dlqs:  # the alarm dimension references the queue resource (QueueName attribute)
        assert any(dlq in d for d in alarms), f"no alarm on {dlq}"


def test_every_alarm_links_a_runbook(app: cdk.App) -> None:
    for name, a in all_resources(app, "AWS::CloudWatch::Alarm").items():
        assert "runbook: https://github.com/avishekdas/sundaydotcom/blob/main/ops/runbooks/" in str(
            a["Properties"]["AlarmDescription"]
        ), name


def test_every_schedule_retries_into_a_dlq(app: cdk.App) -> None:
    schedules = all_resources(app, "AWS::Scheduler::Schedule")
    assert len(schedules) >= 2
    for name, s in schedules.items():
        t = s["Properties"]["Target"]
        assert "DeadLetterConfig" in t and "RetryPolicy" in t, name


def test_singleton_workers_have_concurrency_one(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-workers")
    t.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": "tasklane-dev-outbox-sweeper", "ReservedConcurrentExecutions": 1},
    )
    t.has_resource_properties(
        "AWS::Lambda::Function",
        {"FunctionName": "tasklane-dev-scheduler-tick", "ReservedConcurrentExecutions": 1},
    )


def test_workers_use_the_worker_role_secret_not_admin(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-workers")
    for fn in t.find_resources("AWS::Lambda::Function").values():
        env = fn["Properties"].get("Environment", {}).get("Variables", {})
        if "DB_SECRET_ARN" in env:
            assert "tlworker" in str(env["DB_SECRET_ARN"]).replace("_", ""), env["DB_SECRET_ARN"]


def test_ack_rule_routes_every_tasklane_event_to_the_ack_queue(app: cdk.App) -> None:
    template(app, "tasklane-dev-messaging").has_resource_properties(
        "AWS::Events::Rule",
        {
            "EventPattern": {"source": ["tasklane"]},
            "Targets": Match.array_with(
                [Match.object_like({"DeadLetterConfig": Match.any_value(), "RetryPolicy": Match.any_value()})]
            ),
        },
    )


def test_dead_man_alarm_on_scheduler_tick(app: cdk.App) -> None:
    template(app, "tasklane-dev-workers").has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "MetricName": "Invocations",
            "ComparisonOperator": "LessThanThreshold",
            "TreatMissingData": "breaching",
        },
    )


def test_dev_workers_run_hourly_during_daytime_only(app: cdk.App) -> None:  # D-037
    for s in all_resources(app, "AWS::Scheduler::Schedule").values():
        p = s["Properties"]
        assert p["ScheduleExpression"] == "cron(0 8-19 * * ? *)"
        assert p["ScheduleExpressionTimezone"] == "America/New_York"


def test_dead_man_alarm_tolerates_the_overnight_pause(app: cdk.App) -> None:  # D-037: 12 quiet hours a night
    t = template(app, "tasklane-dev-workers")
    t.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "MetricName": "Invocations",
            "Period": 3600,
            "EvaluationPeriods": 14,
            "DatapointsToAlarm": 14,
            "Threshold": 1,
            "ComparisonOperator": "LessThanThreshold",
            "TreatMissingData": "breaching",
        },
    )


def test_outbox_workers_use_the_outbox_role_and_tick_the_tick_role(app: cdk.App) -> None:  # M0A-4
    fns = template(app, "tasklane-dev-workers").find_resources("AWS::Lambda::Function")
    by_name = {
        f["Properties"].get("FunctionName"): str(f["Properties"]["Environment"]["Variables"]["DB_SECRET_ARN"])
        for f in fns.values()
        if "DB_SECRET_ARN" in f["Properties"].get("Environment", {}).get("Variables", {})
    }
    assert "tlworkeroutbox" in by_name["tasklane-dev-outbox-acker"].replace("_", "")
    assert "tlworkeroutbox" in by_name["tasklane-dev-outbox-sweeper"].replace("_", "")
    assert "tlworkeroutbox" not in by_name["tasklane-dev-scheduler-tick"].replace("_", "")


def test_sweeper_metric_alarms_can_fire_at_the_dev_cadence(app: cdk.App) -> None:  # M0B-2
    alarms = [
        a["Properties"]
        for a in template(app, "tasklane-dev-workers").find_resources("AWS::CloudWatch::Alarm").values()
        if a["Properties"].get("Namespace") == "Tasklane/Outbox"
    ]
    assert len(alarms) == 3
    for a in alarms:  # one datapoint per hour on dev → 1-hour period, alarm on the first breaching datapoint
        assert a["Period"] == 3600 and a["EvaluationPeriods"] == 1 and a.get("DatapointsToAlarm", 1) == 1, a
