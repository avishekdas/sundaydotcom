"""CloudFormation custom-resource entry for the scripted test identities (D-049)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import boto3  # type: ignore[import-untyped]
import pytest
from moto import mock_aws

from tasklane.identity.idp import FakeIdp
from tasklane.platform.db import StrictDataApiFake
from tasklane.workers.test_identities import handler

STORE = "tasklane/dev/test-users/all"


@pytest.fixture
def sm(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("STAGE", "dev")
    monkeypatch.setenv("SECRET_ID", STORE)
    with mock_aws():
        c = boto3.client("secretsmanager", region_name="us-east-1")
        c.create_secret(Name=STORE, SecretString="{}")
        yield c


def _event(kind: str) -> dict[str, Any]:
    return {"RequestType": kind, "PhysicalResourceId": "tasklane-test-identities", "ResourceProperties": {}}


def test_create_writes_credentials_to_the_secret(fresh_db: str, sm: Any) -> None:
    res = handler(_event("Create"), None, idp=FakeIdp(), db=StrictDataApiFake(fresh_db), secrets_client=sm)
    assert res["PhysicalResourceId"] == "tasklane-test-identities"
    stored = json.loads(sm.get_secret_value(SecretId=STORE)["SecretString"])
    assert set(stored) == {"admin", "member", "viewer", "outsider"}
    assert "Data" not in res or "password" not in json.dumps(res["Data"])  # never echo credentials to CFN


def test_update_reuses_stored_passwords(fresh_db: str, sm: Any) -> None:
    idp, db = FakeIdp(), StrictDataApiFake(fresh_db)
    handler(_event("Create"), None, idp=idp, db=db, secrets_client=sm)
    before = sm.get_secret_value(SecretId=STORE)["SecretString"]
    handler(_event("Update"), None, idp=idp, db=db, secrets_client=sm)
    assert json.loads(sm.get_secret_value(SecretId=STORE)["SecretString"]) == json.loads(before)


def test_delete_keeps_users(fresh_db: str, sm: Any) -> None:
    idp, db = FakeIdp(), StrictDataApiFake(fresh_db)
    handler(_event("Create"), None, idp=idp, db=db, secrets_client=sm)
    handler(_event("Delete"), None, idp=idp, db=db, secrets_client=sm)
    assert idp.find_sub("tasklane-test-admin@example.com") is not None
