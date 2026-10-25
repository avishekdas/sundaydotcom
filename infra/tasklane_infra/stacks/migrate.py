"""migrate λ (PE-4): applies SQL migrations through the Data API; invoked by the deploy pipeline."""

from __future__ import annotations

import json

import aws_cdk as cdk
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from tasklane_infra.assets import backend_asset
from tasklane_infra.config import Stage
from tasklane_infra.stacks.data import DataStack


class MigrateStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: Stage, data: DataStack, **kw: object) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        assert data.cluster.secret is not None
        fn = lambda_.Function(
            self,
            "Migrate",
            function_name=f"tasklane-{stage.name}-migrate",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="tasklane.workers.migrate.handler",
            code=lambda_.Code.from_asset(backend_asset()),
            timeout=cdk.Duration.minutes(5),
            memory_size=512,
            log_group=logs.LogGroup(
                self,
                "Logs",
                log_group_name=f"/aws/lambda/tasklane-{stage.name}-migrate",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            ),
            environment={
                "CLUSTER_ARN": data.cluster.cluster_arn,
                "ADMIN_SECRET_ARN": data.cluster.secret.secret_arn,
                "DB_NAME": "tasklane",
                "ROLE_SECRET_ARNS": json.dumps({r: s.secret_arn for r, s in data.role_secrets.items()}),
            },
        )
        data.cluster.grant_data_api_access(fn)
        for secret in data.role_secrets.values():
            secret.grant_read(fn)
        self.function = fn
