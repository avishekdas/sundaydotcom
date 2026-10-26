"""Custom-resource λ for the scripted dev test identities (D-049); only deployed when the stage has test hooks.

Env: STAGE, SECRET_ID (JSON {name: {email, password}}), USER_POOL_ID, CLUSTER_ARN, DB_SECRET_ARN, DB_NAME.
Create/Update ensure the users and store their credentials; Delete keeps them. Credentials never go back to
CloudFormation.
"""

from __future__ import annotations

import json
import os
from typing import Any

from tasklane.identity.idp import CognitoIdp, IdentityProvider
from tasklane.identity.test_identities import ensure_test_identities
from tasklane.platform.data_api import DataApiDb
from tasklane.platform.db import Db

PHYSICAL_ID = "tasklane-test-identities"


def handler(
    event: dict[str, Any],
    context: Any,
    *,
    idp: IdentityProvider | None = None,
    db: Db | None = None,
    secrets_client: Any = None,
) -> dict[str, Any]:
    if event["RequestType"] == "Delete":
        return {"PhysicalResourceId": PHYSICAL_ID}
    if idp is None or db is None or secrets_client is None:
        import boto3  # type: ignore[import-untyped]

        idp = idp or CognitoIdp(boto3.client("cognito-idp"), os.environ["USER_POOL_ID"])
        db = db or DataApiDb(
            boto3.client("rds-data"),
            resource_arn=os.environ["CLUSTER_ARN"],
            secret_arn=os.environ["DB_SECRET_ARN"],
            database=os.environ.get("DB_NAME", "tasklane"),
        )
        secrets_client = secrets_client or boto3.client("secretsmanager")
    secret_id = os.environ["SECRET_ID"]
    existing = json.loads(secrets_client.get_secret_value(SecretId=secret_id)["SecretString"] or "{}")
    creds = ensure_test_identities(idp, db, stage=os.environ["STAGE"], existing=existing)
    secrets_client.put_secret_value(SecretId=secret_id, SecretString=json.dumps(creds))
    return {"PhysicalResourceId": PHYSICAL_ID}
