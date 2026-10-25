"""Data: Aurora Serverless v2 PostgreSQL 18.6 with the Data API, one secret per function-class role (SEC-11, PE-8)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_rds as rds
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from tasklane_infra.config import Stage

ROLES = ("tl_migrator", "tl_api_rw", "tl_reader", "tl_worker", "tl_worker_forms", "tl_audit_writer")


class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: Stage, vpc: ec2.IVpc, **kw: object) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        engine = rds.DatabaseClusterEngine.aurora_postgres(version=rds.AuroraPostgresEngineVersion.VER_18_6)
        params = rds.ParameterGroup(
            self,
            "Params",
            engine=engine,
            parameters={
                "default_toast_compression": "lz4",  # D-028 / PERF-9
                "shared_preload_libraries": "pg_stat_statements,auto_explain",
                "auto_explain.log_min_duration": "1000",
                "log_min_duration_statement": "1000",
            },
        )
        self.cluster = rds.DatabaseCluster(
            self,
            "Cluster",
            engine=engine,
            parameter_group=params,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            credentials=rds.Credentials.from_generated_secret("tl_admin"),
            default_database_name="tasklane",
            writer=rds.ClusterInstance.serverless_v2("writer"),
            serverless_v2_min_capacity=stage.aurora_min_acu,
            serverless_v2_max_capacity=stage.aurora_max_acu,
            enable_data_api=True,
            storage_encrypted=True,
            backup=rds.BackupProps(retention=cdk.Duration.days(7)),
            deletion_protection=False,
            removal_policy=cdk.RemovalPolicy.SNAPSHOT,
        )
        self.role_secrets: dict[str, rds.DatabaseSecret] = {}
        for role in ROLES:
            secret = rds.DatabaseSecret(
                self,
                f"Secret-{role}",
                username=role,
                secret_name=f"tasklane/{stage.name}/db/{role}",
                exclude_characters="\"@/\\'`$",
            )
            self.role_secrets[role] = secret
            ssm.StringParameter(
                self,
                f"SecretArn-{role}",
                parameter_name=f"/tasklane/{stage.name}/db/secret-arn/{role}",
                string_value=secret.secret_arn,
            )
        ssm.StringParameter(
            self,
            "ClusterArn",
            parameter_name=f"/tasklane/{stage.name}/db/cluster-arn",
            string_value=self.cluster.cluster_arn,
        )
        if self.cluster.secret is not None:
            ssm.StringParameter(
                self,
                "AdminSecretArn",
                parameter_name=f"/tasklane/{stage.name}/db/secret-arn/admin",
                string_value=self.cluster.secret.secret_arn,
            )
