"""Realtime (ADR-005): WebSocket API (stage "ws" so CloudFront path /ws maps 1:1), registry table, handlers, fan-out."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_integrations as integ
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from tasklane_infra.config import Stage
from tasklane_infra.constructs import alarm, worker_function
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.messaging import MessagingStack


class RealtimeStack(cdk.Stack):
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
        p = f"tasklane-{stage.name}"
        self.table = ddb.Table(
            self,
            "Registry",
            table_name=f"{p}-realtime",
            partition_key=ddb.Attribute(name="pk", type=ddb.AttributeType.STRING),
            sort_key=ddb.Attribute(name="sk", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        common = {
            "stage": stage,
            "env": {"REALTIME_TABLE": self.table.table_name},
        }
        ws_fn = worker_function(
            self,
            "WsHandlers",
            name="ws-handlers",
            handler="tasklane.workers.ws_handlers.handler",
            timeout=cdk.Duration.seconds(10),
            **common,
        )  # type: ignore[arg-type]
        self.table.grant_read_write_data(ws_fn)
        lam = integ.WebSocketLambdaIntegration
        self.ws_api = apigw.WebSocketApi(
            self,
            "Ws",
            api_name=f"{p}-ws",
            connect_route_options=apigw.WebSocketRouteOptions(integration=lam("ConnectIntegration", ws_fn)),
            disconnect_route_options=apigw.WebSocketRouteOptions(
                integration=lam("DisconnectIntegration", ws_fn)
            ),
            default_route_options=apigw.WebSocketRouteOptions(
                integration=lam("DefaultIntegration", ws_fn), return_response=True
            ),
        )
        self.ws_stage = apigw.WebSocketStage(
            self,
            "WsStage",
            web_socket_api=self.ws_api,
            stage_name="ws",
            auto_deploy=True,
            throttle=apigw.ThrottleSettings(rate_limit=200, burst_limit=400),
        )
        fan = worker_function(
            self,
            "Fanout",
            name="fanout",
            handler="tasklane.workers.fanout.handler",
            timeout=cdk.Duration.seconds(30),
            **common,
        )  # type: ignore[arg-type]
        fan.add_environment("WS_MANAGEMENT_URL", self.ws_stage.callback_url)
        self.table.grant_read_write_data(fan)
        self.ws_stage.grant_management_api_access(fan)
        dlq = sqs.Queue(
            self,
            "FanoutDlq",
            queue_name=f"{p}-fanout-dlq",
            retention_period=cdk.Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )
        alarm(
            self,
            "FanoutDlqDepth",
            metric=dlq.metric_approximate_number_of_messages_visible(period=cdk.Duration.minutes(1)),
            threshold=0,
            comparison=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            runbook="dlq-triage",
            summary=f"Messages in {p}-fanout-dlq",
            topic=messaging.alerts,
        )
        events.Rule(
            self,
            "FanoutRule",
            event_bus=messaging.bus,
            rule_name=f"{p}-fanout",
            event_pattern=events.EventPattern(source=["tasklane"], detail_type=events.Match.prefix("item.")),
            targets=[
                targets.LambdaFunction(
                    fan, dead_letter_queue=dlq, retry_attempts=2, max_event_age=cdk.Duration.minutes(5)
                )
            ],
        )
        self.functions = {"ws-handlers": ws_fn, "fanout": fan}
        self.dlqs = [dlq]
        for aid, fn in (("WsErrors", ws_fn), ("FanoutErrors", fan)):
            alarm(
                self,
                aid,
                metric=fn.metric_errors(period=cdk.Duration.minutes(5)),
                threshold=0,
                comparison=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                runbook="realtime",
                summary=f"{fn.function_name} errors",
                topic=messaging.alerts,
            )
