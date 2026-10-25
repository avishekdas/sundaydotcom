"""Shared λ wiring: the Data API Db for this function's role, from env."""

from __future__ import annotations

import os
from typing import Any

from tasklane.platform.data_api import DataApiDb


def boto(name: str) -> Any:
    import boto3  # type: ignore[import-untyped]

    return boto3.client(name)


def db_from_env(rds_client: Any = None) -> DataApiDb:
    return DataApiDb(
        rds_client or boto("rds-data"),
        resource_arn=os.environ["CLUSTER_ARN"],
        secret_arn=os.environ["DB_SECRET_ARN"],
        database=os.environ.get("DB_NAME", "tasklane"),
    )
