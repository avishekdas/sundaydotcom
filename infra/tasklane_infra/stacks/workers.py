"""Workers: outbox-acker, outbox-sweeper, scheduler-tick (arch 05 §5.1; PE-5, PE-10)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_scheduler as scheduler
from constructs import Construct

from tasklane_infra.config import Stage
from tasklane_infra.constructs import alarm, worker_function
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.messaging import MessagingStack

GT = cw.ComparisonOperator.GREATER_THAN_THRESHOLD


class WorkersStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        stage: Stage,
        data: DataStack,
        messaging: MessagingStack,
        **kw: object,
    ) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        secret = data.role_secrets["tl_worker"]
        common = {"stage": stage, "cluster": data.cluster, "db_secret": secret}
        acker = worker_function(
            self, "Acker", name="outbox-acker", handler="tasklane.workers.outbox_acker.handler", **common
        )
        acker.add_event_source(
            sources.SqsEventSource(
                messaging.ack_queue,
                batch_size=10,
                max_batching_window=cdk.Duration.seconds(2),
                report_batch_item_failures=True,
            )
        )
        sweeper = worker_function(
            self,
            "Sweeper",
            name="outbox-sweeper",
            handler="tasklane.workers.outbox_sweeper.handler",
            reserved=1,
            timeout=cdk.Duration.seconds(55),
            env={"EVENT_BUS_NAME": messaging.bus.event_bus_name},
            **common,
        )
        messaging.bus.grant_put_events_to(sweeper)
        tick = worker_function(
            self,
            "Tick",
            name="scheduler-tick",
            handler="tasklane.workers.scheduler_tick.handler",
            reserved=1,
            timeout=cdk.Duration.seconds(55),
            **common,
        )

        role = iam.Role(self, "SchedulerRole", assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"))
        messaging.schedule_dlq.grant_send_messages(role)
        for fid, fn in (("SweeperSchedule", sweeper), ("TickSchedule", tick)):
            fn.grant_invoke(role)
            scheduler.CfnSchedule(
                self,
                fid,
                name=f"tasklane-{stage.name}-{fid[0].lower()}{fid[1:]}",
                schedule_expression=stage.worker_schedule,
                schedule_expression_timezone=stage.worker_schedule_tz,
                flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(mode="OFF"),
                target=scheduler.CfnSchedule.TargetProperty(
                    arn=fn.function_arn,
                    role_arn=role.role_arn,
                    retry_policy=scheduler.CfnSchedule.RetryPolicyProperty(
                        maximum_retry_attempts=2, maximum_event_age_in_seconds=300
                    ),
                    dead_letter_config=scheduler.CfnSchedule.DeadLetterConfigProperty(
                        arn=messaging.schedule_dlq.queue_arn
                    ),
                ),
            )

        t = messaging.alerts
        for aid, fn, book in (
            ("AckerErrors", acker, "outbox-acker"),
            ("SweeperErrors", sweeper, "outbox-circuit"),
            ("TickErrors", tick, "scheduler-tick"),
        ):
            alarm(
                self,
                aid,
                metric=fn.metric_errors(period=cdk.Duration.minutes(5)),
                threshold=0,
                comparison=GT,
                runbook=book,
                summary=f"{fn.function_name} errors",
                topic=t,
            )
        alarm(
            self,
            "TickDeadMan",
            metric=tick.metric_invocations(
                period=cdk.Duration.hours(1) if stage.dead_man_hours else cdk.Duration.minutes(5),
                statistic="Sum",
            ),
            threshold=1 if stage.dead_man_hours else 3,
            evaluation_periods=stage.dead_man_hours or 1,
            datapoints=stage.dead_man_hours or None,
            comparison=cw.ComparisonOperator.LESS_THAN_THRESHOLD,
            runbook="scheduler-tick",
            summary="scheduler-tick is not running (dead-man switch)",
            topic=t,
            missing=cw.TreatMissingData.BREACHING,
        )

        ns = "Tasklane/Outbox"
        for mid, field, thr, book, summ in (
            ("Backlog", "backlog", 1000, "outbox-circuit", "Outbox backlog > 1,000"),
            ("MaxAttempts", "max_attempts", 3, "outbox-circuit", "Outbox rows retried > 3 times"),
            ("Circuit", "circuit_open", 0, "outbox-circuit", "Outbox sweeper circuit open (acker broken?)"),
        ):
            logs.MetricFilter(
                self,
                f"{mid}Filter",
                log_group=sweeper.log_group,  # type: ignore[arg-type]
                filter_pattern=logs.FilterPattern.literal('{ $.metric = "outbox.sweep" }'),
                metric_namespace=ns,
                metric_name=mid,
                metric_value=f"$.{field}" if field != "circuit_open" else "$.circuit_open",
            )
            alarm(
                self,
                f"{mid}Alarm",
                metric=cw.Metric(
                    namespace=ns, metric_name=mid, statistic="Maximum", period=cdk.Duration.minutes(1)
                ),
                threshold=thr,
                comparison=GT,
                runbook=book,
                summary=summ,
                topic=t,
                evaluation_periods=3,
            )
        self.functions: dict[str, lambda_.Function] = {"acker": acker, "sweeper": sweeper, "tick": tick}
