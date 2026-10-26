"""Bootstrap admin (K7.6, A1.1, D-055): a custom resource that makes the configured email an Admin (Cognito invite on
the first deploy) and ensures the default workspace. Built for every stage that sets ``bootstrap_admin_email``."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import custom_resources as cr
from constructs import Construct

from tasklane_infra.assets import backend_asset
from tasklane_infra.config import Stage
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.identity import IdentityStack


class BootstrapStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        stage: Stage,
        data: DataStack,
        identity: IdentityStack,
        **kw: object,
    ) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        if not stage.bootstrap_admin_email:
            raise ValueError("bootstrap needs stage.bootstrap_admin_email")
        db_secret = data.role_secrets["tl_api_rw"]
        fn = lambda_.Function(
            self,
            "Fn",
            function_name=f"tasklane-{stage.name}-bootstrap",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="tasklane.workers.bootstrap.handler",
            code=lambda_.Code.from_asset(backend_asset()),
            timeout=cdk.Duration.minutes(2),
            memory_size=256,
            log_group=logs.LogGroup(
                self,
                "Logs",
                log_group_name=f"/aws/lambda/tasklane-{stage.name}-bootstrap",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            ),
            environment={
                "ADMIN_EMAIL": stage.bootstrap_admin_email,
                "USER_POOL_ID": identity.pool.user_pool_id,
                "CLUSTER_ARN": data.cluster.cluster_arn,
                "DB_SECRET_ARN": db_secret.secret_arn,
                "DB_NAME": "tasklane",
            },
        )
        db_secret.grant_read(fn)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"],
                resources=[data.cluster.cluster_arn],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:AdminCreateUser", "cognito-idp:AdminGetUser"],
                resources=[identity.pool.user_pool_arn],
            )
        )
        provider = cr.Provider(
            self, "Provider", on_event_handler=fn, log_retention=logs.RetentionDays.ONE_WEEK
        )
        cdk.CustomResource(
            self,
            "Admin",
            service_token=provider.service_token,
            resource_type="Custom::Bootstrap",
            properties={"Email": stage.bootstrap_admin_email},
        )
