"""Api (ADR-003): HTTP API with a Cognito JWT authorizer in front of the `api` Lambdalith."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_authorizers as authz
from aws_cdk import aws_apigatewayv2_integrations as integ
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_codedeploy as codedeploy
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from tasklane_infra.assets import backend_asset
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
        # Rate-limit counters (arch 03 §3.8): sign-in per (email, IP) and per account, refresh per IP.
        counters = ddb.Table(
            self,
            "Counters",
            table_name=f"tasklane-{stage.name}-counters",
            partition_key=ddb.Attribute(name="pk", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        self.counters = counters
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
                "USER_POOL_ID": identity.pool.user_pool_id,
                "COGNITO_CLIENT_ID": identity.proxy_client.user_pool_client_id,
                "COUNTERS_TABLE": counters.table_name,
                "ORIGIN_SECRET": identity.origin_secret_ref,
                "AUDIT_SECRET_ARN": data.role_secrets["tl_audit_writer"].secret_arn,  # D-056
            },
        )
        data.role_secrets["tl_audit_writer"].grant_read(fn)
        counters.grant_read_write_data(fn)
        # Auth proxy inside the api λ (D-051, a recorded deviation from SEC-11): only the Cognito actions it uses,
        # on this pool only. RevokeToken needs no IAM permission (it takes the client id).
        fn.add_to_role_policy(
            cdk.aws_iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminInitiateAuth",
                    "cognito-idp:AdminRespondToAuthChallenge",
                    "cognito-idp:AdminUserGlobalSignOut",
                    # user administration (F1, D-054): invite, revoke, deactivate / reactivate, lookup
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminDeleteUser",
                    "cognito-idp:AdminDisableUser",
                    "cognito-idp:AdminEnableUser",
                    "cognito-idp:AdminGetUser",
                ],
                resources=[identity.pool.user_pool_arn],
            )
        )
        fn.add_to_role_policy(
            cdk.aws_iam.PolicyStatement(actions=["events:PutEvents"], resources=[messaging.bus.event_bus_arn])
        )
        realtime.table.grant_read_write_data(fn)
        # Deploy safety (PE-6): traffic goes to the `live` alias; CodeDeploy shifts 10 % for 5 minutes and rolls
        # back automatically when the alias error alarm fires.
        live = lambda_.Alias(self, "Live", alias_name="live", version=fn.current_version)
        canary_alarm = cw.Alarm(
            self,
            "LiveErrors",
            metric=live.metric_errors(period=cdk.Duration.minutes(1)),
            threshold=0,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=1,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            alarm_description="api live alias errors during/after a deploy — runbook: "
            "https://github.com/avishekdas/sundaydotcom/blob/main/ops/runbooks/bad-deploy.md",
        )
        canary_alarm.add_alarm_action(cdk.aws_cloudwatch_actions.SnsAction(messaging.alerts))
        # M0B-6: before any traffic shifts, a hook invokes the new version's /api/v1/health (DB round trip); a
        # failure stops the deployment. The canary window itself gets real traffic only once users exist.
        hook = lambda_.Function(
            self,
            "PredeployHook",
            function_name=f"tasklane-{stage.name}-predeploy-hook",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="tasklane.workers.predeploy_hook.handler",
            code=lambda_.Code.from_asset(backend_asset()),
            timeout=cdk.Duration.seconds(60),
            memory_size=256,
            environment={
                "TARGET_VERSION_ARN": fn.current_version.function_arn,
                "ORIGIN_SECRET": identity.origin_secret_ref,
            },
            log_group=logs.LogGroup(
                self,
                "PredeployHookLogs",
                log_group_name=f"/aws/lambda/tasklane-{stage.name}-predeploy-hook",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            ),
        )
        fn.current_version.grant_invoke(hook)
        codedeploy.LambdaDeploymentGroup(
            self,
            "Canary",
            alias=live,
            pre_hook=hook,
            deployment_config=codedeploy.LambdaDeploymentConfig.CANARY_10_PERCENT_5_MINUTES,
            alarms=[canary_alarm],
            auto_rollback=codedeploy.AutoRollbackConfig(failed_deployment=True, deployment_in_alarm=True),
        )
        jwt = authz.HttpJwtAuthorizer(
            "Jwt", identity.issuer, jwt_audience=[identity.proxy_client.user_pool_client_id]
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
            integration=integ.HttpLambdaIntegration("ApiIntegration", live),
        )
        self.http_api.add_routes(  # auth proxy: public, protected by the origin secret and its own counters
            path="/api/auth/{proxy+}",
            methods=[apigw.HttpMethod.ANY],
            integration=integ.HttpLambdaIntegration("AuthIntegration", live),
            authorizer=apigw.HttpNoneAuthorizer(),
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
        closed = logs.MetricFilter(
            self,
            "AccountClosedFilter",
            log_group=fn.log_group,
            metric_namespace="Tasklane/Auth",
            metric_name="AccountClosed",
            filter_pattern=logs.FilterPattern.literal('{ $.metric = "auth.account_closed" }'),
            metric_value="1",
        )
        alarm(
            self,
            "AccountClosed",
            metric=closed.metric(period=cdk.Duration.minutes(5), statistic="Sum"),
            threshold=0,
            comparison=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            runbook="auth",
            summary="Sev2: an account's sign-in was closed after 10 failures in 15 min (D-044)",
            topic=messaging.alerts,
        )
        self.function = fn
        self.live = live
