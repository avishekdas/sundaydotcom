"""Messaging (ADR-004): event bus, outbox-ack queue, delivery-contract DLQs and alarms, alert topic."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from tasklane_infra.config import Stage
from tasklane_infra.constructs import alarm


class MessagingStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: Stage, **kw: object) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        p = f"tasklane-{stage.name}"
        self.alerts = sns.Topic(
            self, "Alerts", topic_name=f"{p}-alerts"
        )  # subscriptions: ops/runbooks/README
        self.bus = events.EventBus(self, "Bus", event_bus_name=p)

        def dlq(id_: str, name: str) -> sqs.Queue:
            q = sqs.Queue(
                self,
                id_,
                queue_name=f"{p}-{name}-dlq",
                retention_period=cdk.Duration.days(14),
                encryption=sqs.QueueEncryption.SQS_MANAGED,
            )
            alarm(
                self,
                f"{id_}Depth",
                metric=q.metric_approximate_number_of_messages_visible(period=cdk.Duration.minutes(1)),
                threshold=0,
                comparison=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                runbook="dlq-triage",
                summary=f"Messages in {p}-{name}-dlq",
                topic=self.alerts,
            )
            return q

        ack_dlq = dlq("AckDlq", "outbox-ack")
        self.ack_queue = sqs.Queue(
            self,
            "AckQueue",
            queue_name=f"{p}-outbox-ack",
            visibility_timeout=cdk.Duration.seconds(120),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            dead_letter_queue=sqs.DeadLetterQueue(queue=ack_dlq, max_receive_count=5),
        )
        self.rule_dlq = dlq("RuleDlq", "rule-targets")
        self.schedule_dlq = dlq("ScheduleDlq", "schedules")
        events.Rule(
            self,
            "AckRule",
            event_bus=self.bus,
            rule_name=f"{p}-outbox-ack",
            event_pattern=events.EventPattern(source=["tasklane"]),
            targets=[
                targets.SqsQueue(
                    self.ack_queue,
                    dead_letter_queue=self.rule_dlq,
                    retry_attempts=8,
                    max_event_age=cdk.Duration.hours(24),
                )
            ],
        )
