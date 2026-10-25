"""Api (ADR-003): HTTP API with a Cognito JWT authorizer in front of the `api` Lambdalith."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_authorizers as authz
from aws_cdk import aws_apigatewayv2_integrations as integ
from aws_cdk import aws_cloudwatch as cw
from constructs import Construct

from tasklane_infra.config import Stage
from tasklane_infra.constructs import alarm, worker_function
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.identity import IdentityStack
from tasklane_infra.stacks.messaging import MessagingStack
from tasklane_infra.stacks.realtime import RealtimeStack


class ApiStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        stage: Stage,
        data: DataStack,
        identity: IdentityStack,
        messaging: MessagingStack,
        realtime: RealtimeStack,
        **kw: object,
    ) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        fn = worker_function(
            self,
            "Api",
            stage=stage,
            name="api",
            handler="tasklane.api.app.handler",
            cluster=data.cluster,
            db_secret=data.role_secrets["tl_api_rw"],
            timeout=cdk.Duration.seconds(29),
            env={
                "EVENT_BUS_NAME": messaging.bus.event_bus_name,
                "REALTIME_TABLE": realtime.table.table_name,
                "WS_URL": "/ws",
                "POWERTOOLS_SERVICE_NAME": "api",
            },
        )
        fn.add_to_role_policy(
            cdk.aws_iam.PolicyStatement(actions=["events:PutEvents"], resources=[messaging.bus.event_bus_arn])
        )
        realtime.table.grant_read_write_data(fn)
        jwt = authz.HttpJwtAuthorizer(
            "Jwt", identity.issuer, jwt_audience=[identity.client.user_pool_client_id]
        )
        self.http_api = apigw.HttpApi(
            self,
            "Http",
            api_name=f"tasklane-{stage.name}-http",
            default_authorizer=jwt,
            create_default_stage=True,
        )
        self.http_api.add_routes(
            path="/api/v1/{proxy+}",
            methods=[apigw.HttpMethod.ANY],
            integration=integ.HttpLambdaIntegration("ApiIntegration", fn),
        )
        alarm(
            self,
            "ApiErrors",
            metric=fn.metric_errors(period=cdk.Duration.minutes(5)),
            threshold=0,
            comparison=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            runbook="api",
            summary="api λ errors",
            topic=messaging.alerts,
        )
        self.function = fn
