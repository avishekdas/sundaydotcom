"""Shared constructs: worker functions with a role-scoped DB secret, alarms that always carry a runbook."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_rds as rds
from aws_cdk import aws_sns as sns
from constructs import Construct

from tasklane_infra.assets import backend_asset
from tasklane_infra.config import Stage

DEFAULT_TIMEOUT = cdk.Duration.seconds(60)
RUNBOOKS = "https://github.com/avishekdas/sundaydotcom/blob/main/ops/runbooks/"


def worker_function(
    scope: Construct,
    id: str,
    *,
    stage: Stage,
    name: str,
    handler: str,
    cluster: rds.DatabaseCluster | None = None,
    db_secret: rds.DatabaseSecret | None = None,
    reserved: int | None = None,
    timeout: cdk.Duration = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
) -> lambda_.Function:
    fn_name = f"tasklane-{stage.name}-{name}"
    fn = lambda_.Function(
        scope,
        id,
        function_name=fn_name,
        runtime=lambda_.Runtime.PYTHON_3_13,
        architecture=lambda_.Architecture.ARM_64,
        handler=handler,
        code=lambda_.Code.from_asset(backend_asset()),
        timeout=timeout,
        memory_size=512,
        reserved_concurrent_executions=reserved,
        log_group=logs.LogGroup(
            scope,
            f"{id}Logs",
            log_group_name=f"/aws/lambda/{fn_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        ),
        environment={
            **(
                {
                    "CLUSTER_ARN": cluster.cluster_arn,
                    "DB_SECRET_ARN": db_secret.secret_arn,
                    "DB_NAME": "tasklane",
                }
                if cluster is not None and db_secret is not None
                else {}
            ),
            "STAGE": stage.name,
            **(env or {}),
        },
    )
    if cluster is None or db_secret is None:  # no database access at all (M0B-8)
        return fn
    # Data API on the cluster + read of this function's own role secret only (not the admin secret)
    fn.add_to_role_policy(
        iam.PolicyStatement(
            actions=[
                "rds-data:ExecuteStatement",
                "rds-data:BatchExecuteStatement",
                "rds-data:BeginTransaction",
                "rds-data:CommitTransaction",
                "rds-data:RollbackTransaction",
            ],
            resources=[cluster.cluster_arn],
        )
    )
    db_secret.grant_read(fn)
    return fn


def alarm(
    scope: Construct,
    id: str,
    *,
    metric: cw.IMetric,
    threshold: float,
    comparison: cw.ComparisonOperator,
    runbook: str,
    summary: str,
    topic: sns.ITopic,
    evaluation_periods: int = 1,
    datapoints: int | None = None,
    missing: cw.TreatMissingData = cw.TreatMissingData.NOT_BREACHING,
) -> cw.Alarm:
    a = cw.Alarm(
        scope,
        id,
        metric=metric,
        threshold=threshold,
        comparison_operator=comparison,
        evaluation_periods=evaluation_periods,
        datapoints_to_alarm=datapoints,
        treat_missing_data=missing,
        alarm_description=f"{summary} — runbook: {RUNBOOKS}{runbook}.md",
    )
    a.add_alarm_action(cw_actions.SnsAction(topic))
    return a
