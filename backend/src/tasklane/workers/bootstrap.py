"""Custom-resource λ for the bootstrap admin (K7.6, D-055). Env: ADMIN_EMAIL, USER_POOL_ID, CLUSTER_ARN,
DB_SECRET_ARN, DB_NAME. Create/Update ensure the admin and the default workspace; Delete keeps everything."""

from __future__ import annotations

import os
from typing import Any

from tasklane.identity.bootstrap import ensure_bootstrap
from tasklane.identity.idp import CognitoIdp, IdentityProvider
from tasklane.platform.data_api import DataApiDb
from tasklane.platform.db import Db

PHYSICAL_ID = "tasklane-bootstrap"


def handler(
    event: dict[str, Any], context: Any, *, idp: IdentityProvider | None = None, db: Db | None = None
) -> dict[str, Any]:
    if event["RequestType"] == "Delete":
        return {"PhysicalResourceId": PHYSICAL_ID}
    if idp is None or db is None:
        import boto3  # type: ignore[import-untyped]

        idp = idp or CognitoIdp(boto3.client("cognito-idp"), os.environ["USER_POOL_ID"])
        db = db or DataApiDb(
            boto3.client("rds-data"),
            resource_arn=os.environ["CLUSTER_ARN"],
            secret_arn=os.environ["DB_SECRET_ARN"],
            database=os.environ.get("DB_NAME", "tasklane"),
        )
    ensure_bootstrap(db, idp, os.environ["ADMIN_EMAIL"])
    return {"PhysicalResourceId": PHYSICAL_ID}
