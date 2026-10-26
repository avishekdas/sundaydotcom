"""Scripted dev test identities (PE-17, M0B-24, D-049): a custom resource creating admin / member / viewer /
outsider in Cognito and `tl.users`, credentials in one secret. Built only for stages with test hooks (never prod)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import custom_resources as cr
from constructs import Construct

from tasklane_infra.assets import backend_asset
from tasklane_infra.config import Stage
from tasklane_infra.stacks.data import DataStack
from tasklane_infra.stacks.identity import IdentityStack

USERS = "admin,member,viewer,outsider"


class TestIdentitiesStack(cdk.Stack):
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
        if stage.name == "prod" or not stage.test_hooks:
            raise ValueError("test identities exist only on stages with test hooks, never prod")
        store = sm.Secret(
            self,
            "Store",
            secret_name=f"tasklane/{stage.name}/test-users/all",
            secret_string_value=cdk.SecretValue.unsafe_plain_text("{}"),  # filled by the custom resource
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        db_secret = data.role_secrets["tl_api_rw"]
        assert data.cluster.secret is not None
        fn = lambda_.Function(
            self,
            "Fn",
            function_name=f"tasklane-{stage.name}-test-identities",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="tasklane.workers.test_identities.handler",
            code=lambda_.Code.from_asset(backend_asset()),
            timeout=cdk.Duration.minutes(2),
            memory_size=256,
            log_group=logs.LogGroup(
                self,
                "Logs",
                log_group_name=f"/aws/lambda/tasklane-{stage.name}-test-identities",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=cdk.RemovalPolicy.DESTROY,
            ),
            environment={
                "STAGE": stage.name,
                "SECRET_ID": store.secret_arn,
                "USER_POOL_ID": identity.pool.user_pool_id,
                "CLUSTER_ARN": data.cluster.cluster_arn,
                "DB_SECRET_ARN": db_secret.secret_arn,
                "DB_NAME": "tasklane",
            },
        )
        store.grant_read(fn)
        store.grant_write(fn)
        db_secret.grant_read(fn)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"],
                resources=[data.cluster.cluster_arn],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:AdminCreateUser",
                    "cognito-idp:AdminSetUserPassword",
                    "cognito-idp:AdminGetUser",
                ],
                resources=[identity.pool.user_pool_arn],
            )
        )
        provider = cr.Provider(
            self, "Provider", on_event_handler=fn, log_retention=logs.RetentionDays.ONE_WEEK
        )
        cdk.CustomResource(
            self,
            "Users",
            service_token=provider.service_token,
            resource_type="Custom::TestIdentities",
            properties={"Users": USERS, "Version": "1"},
        )
