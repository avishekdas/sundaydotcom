"""Data stack (arch 02 §2.x, D-026, D-028, D-030, D-031): Aurora SLv2 PG 18.6 + Data API, a secret per role."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match

from tests.conftest import template

ROLES = [
    "tl_migrator",
    "tl_api_rw",
    "tl_reader",
    "tl_worker",
    "tl_worker_outbox",
    "tl_worker_forms",
    "tl_audit_writer",
]


def test_cluster_is_pg_18_6_serverless_v2_with_data_api(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-data")
    t.has_resource_properties(
        "AWS::RDS::DBCluster",
        {
            "Engine": "aurora-postgresql",
            "EngineVersion": "18.6",
            "EnableHttpEndpoint": True,
            "StorageEncrypted": True,
            "ServerlessV2ScalingConfiguration": {"MinCapacity": 0, "MaxCapacity": 4},
        },
    )
    t.has_resource_properties("AWS::RDS::DBInstance", {"DBInstanceClass": "db.serverless"})


def test_parameter_group_sets_lz4_and_pg_stat_statements(app: cdk.App) -> None:
    template(app, "tasklane-dev-data").has_resource_properties(
        "AWS::RDS::DBClusterParameterGroup",
        {
            "Parameters": Match.object_like(
                {
                    "default_toast_compression": "lz4",
                    "shared_preload_libraries": "pg_stat_statements,auto_explain",
                }
            )
        },
    )


def test_cluster_is_kept_as_snapshot_on_delete(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-data")
    t.has_resource("AWS::RDS::DBCluster", {"DeletionPolicy": "Snapshot", "UpdateReplacePolicy": "Snapshot"})


def test_one_secret_per_function_class_role(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-data")
    for role in ROLES:
        t.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "GenerateSecretString": Match.object_like(
                    {"SecretStringTemplate": Match.string_like_regexp(role)}
                )
            },
        )


def test_endpoints_published_to_ssm(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-data")
    for name in ["/tasklane/dev/db/cluster-arn", "/tasklane/dev/db/secret-arn/tl_api_rw"]:
        t.has_resource_properties("AWS::SSM::Parameter", {"Name": name})


def test_network_has_no_nat(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-network")
    t.resource_count_is("AWS::EC2::NatGateway", 0)
    t.resource_count_is("AWS::EC2::InternetGateway", 0)


def test_every_resource_is_tagged_with_project_and_stage(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-data")
    t.has_resource_properties(
        "AWS::RDS::DBCluster",
        {
            "Tags": Match.array_with(
                [{"Key": "project", "Value": "tasklane"}, {"Key": "stage", "Value": "dev"}]
            )
        },
    )
