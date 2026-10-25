"""Observability: account audit trail and the stage dashboard (PE-7, SEC-20 as scoped by D-039)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudtrail as cloudtrail
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_s3 as s3
from constructs import Construct

from tasklane_infra.config import Stage
from tasklane_infra.stacks.api import ApiStack
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.messaging import MessagingStack
from tasklane_infra.stacks.realtime import RealtimeStack
from tasklane_infra.stacks.workers import WorkersStack


class ObservabilityStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        stage: Stage,
        data: DataStack,
        messaging: MessagingStack,
        workers: WorkersStack,
        api: ApiStack,
        realtime: RealtimeStack,
        **kw: object,
    ) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        if "cloudtrail" in stage.security_baseline:
            bucket = s3.Bucket(
                self,
                "TrailLogs",
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                encryption=s3.BucketEncryption.S3_MANAGED,
                enforce_ssl=True,
                versioned=False,
                lifecycle_rules=[s3.LifecycleRule(expiration=cdk.Duration.days(365))],
                removal_policy=cdk.RemovalPolicy.RETAIN,
            )
            cloudtrail.Trail(
                self,
                "Trail",
                trail_name=f"tasklane-{stage.name}-account",
                bucket=bucket,
                is_multi_region_trail=True,
                include_global_service_events=True,
                enable_file_validation=True,
                send_to_cloud_watch_logs=False,
            )
        five = cdk.Duration.minutes(5)
        fns = {"api": api.function, **workers.functions}
        dash = cw.Dashboard(self, "Dash", dashboard_name=f"tasklane-{stage.name}")
        dash.add_widgets(
            cw.GraphWidget(
                title="Lambda errors",
                width=12,
                left=[f.metric_errors(period=five, label=n) for n, f in fns.items()],
            ),
            cw.GraphWidget(
                title="api duration p95 (ms)",
                width=12,
                left=[api.function.metric_duration(period=five, statistic="p95")],
            ),
        )
        dash.add_widgets(
            cw.GraphWidget(
                title="Outbox sweeper",
                width=12,
                left=[
                    cw.Metric(
                        namespace="Tasklane/Outbox", metric_name=m, statistic="Maximum", period=five, label=m
                    )
                    for m in ("Backlog", "MaxAttempts", "Circuit")
                ],
            ),
            cw.GraphWidget(
                title="Aurora ACU",
                width=12,
                left=[
                    cw.Metric(
                        namespace="AWS/RDS",
                        metric_name="ServerlessDatabaseCapacity",
                        statistic="Average",
                        period=five,
                        dimensions_map={"DBClusterIdentifier": data.cluster.cluster_identifier},
                    )
                ],
            ),
        )
        dash.add_widgets(
            cw.GraphWidget(
                title="Ack queue depth",
                width=12,
                left=[messaging.ack_queue.metric_approximate_number_of_messages_visible(period=five)],
            ),
            cw.GraphWidget(
                title="WebSocket connections / messages",
                width=12,
                left=[
                    cw.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="ConnectCount",
                        statistic="Sum",
                        period=five,
                        dimensions_map={"ApiId": realtime.ws_api.api_id, "Stage": "ws"},
                    ),
                    cw.Metric(
                        namespace="AWS/ApiGateway",
                        metric_name="MessageCount",
                        statistic="Sum",
                        period=five,
                        dimensions_map={"ApiId": realtime.ws_api.api_id, "Stage": "ws"},
                    ),
                ],
            ),
        )
