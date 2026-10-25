"""migrate λ stack (PE-4): Data API + per-role secret access, packaged with the SQL migrations."""

from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
from aws_cdk.assertions import Match

from tasklane_infra.assets import backend_asset
from tests.conftest import template


def test_function_is_python_313_arm64_with_db_env(app: cdk.App) -> None:
    template(app, "tasklane-dev-migrate").has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "tasklane-dev-migrate",
            "Runtime": "python3.13",
            "Architectures": ["arm64"],
            "Handler": "tasklane.workers.migrate.handler",
            "Timeout": 300,
            "Environment": {
                "Variables": Match.object_like(
                    {
                        "DB_NAME": "tasklane",
                        "CLUSTER_ARN": Match.any_value(),
                        "ADMIN_SECRET_ARN": Match.any_value(),
                        "ROLE_SECRET_ARNS": Match.any_value(),
                    }
                )
            },
        },
    )


def test_function_may_use_the_data_api(app: cdk.App) -> None:
    template(app, "tasklane-dev-migrate").has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Action": Match.array_with(
                                    ["rds-data:BeginTransaction", "rds-data:ExecuteStatement"]
                                )
                            }
                        )
                    ]
                )
            }
        },
    )


def test_asset_contains_package_and_migrations() -> None:
    root = Path(backend_asset())
    assert (root / "tasklane" / "workers" / "migrate.py").exists()
    assert (root / "tasklane" / "migrations_sql" / "0001_init.sql").exists()
    assert not list(root.rglob("__pycache__"))


def test_asset_bundles_third_party_wheels_for_arm64() -> None:
    root = Path(backend_asset())
    assert (root / "aws_lambda_powertools").is_dir() and (root / "pydantic").is_dir()
    so = list((root / "pydantic_core").glob("*.so"))
    assert so and "aarch64" in so[0].name
    assert not (root / "boto3").exists()  # provided by the runtime
