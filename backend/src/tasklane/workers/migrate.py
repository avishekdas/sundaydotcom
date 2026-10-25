"""migrate λ (PE-4): invoked by the deploy pipeline after the Data stack, before code stacks.

Env: CLUSTER_ARN, ADMIN_SECRET_ARN, DB_NAME, ROLE_SECRET_ARNS (JSON {role: secret arn}).
Applies pending migrations through the Data API, then (re)sets each role's LOGIN password from its secret.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tasklane.platform.data_api import DataApiDb
from tasklane.platform.migrations import apply_migrations, ensure_role_logins

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations_sql"
if not MIGRATIONS_DIR.exists():  # source checkout: backend/migrations
    MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def handler(
    event: dict[str, Any], context: Any, *, rds_client: Any = None, secrets_client: Any = None
) -> dict[str, Any]:
    if rds_client is None or secrets_client is None:
        import boto3  # type: ignore[import-untyped]

        rds_client = rds_client or boto3.client("rds-data")
        secrets_client = secrets_client or boto3.client("secretsmanager")
    db = DataApiDb(
        rds_client,
        resource_arn=os.environ["CLUSTER_ARN"],
        secret_arn=os.environ["ADMIN_SECRET_ARN"],
        database=os.environ.get("DB_NAME", "tasklane"),
    )
    applied = apply_migrations(db, MIGRATIONS_DIR)
    role_arns: dict[str, str] = json.loads(os.environ.get("ROLE_SECRET_ARNS", "{}"))
    passwords = {
        role: json.loads(secrets_client.get_secret_value(SecretId=arn)["SecretString"])["password"]
        for role, arn in role_arns.items()
    }
    ensure_role_logins(db, passwords)
    return {"applied": applied, "roles": sorted(passwords)}
