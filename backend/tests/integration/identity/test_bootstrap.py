"""Bootstrap admin at deployment (K7.6, A1.1, D-055): the configured email becomes an Admin — invited through
Cognito on the first deploy, never re-invited — and a default "Main workspace" exists (A2.3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from tasklane.identity.auth_backend import FakeAuthBackend
from tasklane.identity.bootstrap import ensure_bootstrap
from tasklane.platform.clock import FakeClock
from tasklane.platform.db import StrictDataApiFake
from tasklane.workers.bootstrap import handler

pytestmark = pytest.mark.integration
EMAIL = "Owner@Example.com"


def _users(db: StrictDataApiFake) -> dict[str, dict[str, Any]]:
    rows = db.query("select email::text as email, role, status from tl.users")
    return {r["email"]: dict(r) for r in rows}


def _default_ws(db: StrictDataApiFake) -> list[str]:
    return [
        r["name"] for r in db.query("select name from tl.workspaces where is_default and state = 'active'")
    ]


def test_first_deploy_invites_the_admin_and_creates_the_default_workspace(fresh_db: str) -> None:
    db, idp = StrictDataApiFake(fresh_db), FakeAuthBackend(FakeClock(datetime(2026, 10, 26, tzinfo=UTC)))
    ensure_bootstrap(db, idp, EMAIL)
    assert _users(db)["owner@example.com"] == {
        "email": "owner@example.com",
        "role": "admin",
        "status": "invited",
    }
    assert idp.invites_sent("owner@example.com") == 1
    assert _default_ws(db) == ["Main workspace"]


def test_rerun_changes_nothing(fresh_db: str) -> None:
    db, idp = StrictDataApiFake(fresh_db), FakeAuthBackend(FakeClock(datetime(2026, 10, 26, tzinfo=UTC)))
    ensure_bootstrap(db, idp, EMAIL)
    ensure_bootstrap(db, idp, EMAIL)
    assert idp.invites_sent("owner@example.com") == 1
    assert _default_ws(db) == ["Main workspace"]


def test_existing_user_is_promoted_and_existing_default_workspace_kept(fresh_db: str) -> None:
    db, idp = StrictDataApiFake(fresh_db), FakeAuthBackend(FakeClock(datetime(2026, 10, 26, tzinfo=UTC)))
    sub = idp.create_user("owner@example.com", "Owner")
    db.execute(
        "insert into tl.users (cognito_sub, email, name, role, status) values (:s::uuid, 'owner@example.com', 'O', "
        "'member', 'active')",
        {"s": sub},
    )
    db.execute(
        "insert into tl.workspaces (name, kind, position, is_default) values ('Home', 'open', 'a', true)"
    )
    ensure_bootstrap(db, idp, EMAIL)
    assert _users(db)["owner@example.com"]["role"] == "admin"
    assert _users(db)["owner@example.com"]["status"] == "active"
    assert idp.invites_sent("owner@example.com") == 0
    assert _default_ws(db) == ["Home"]


def test_cognito_user_without_a_row_is_adopted_as_active(fresh_db: str) -> None:
    db, idp = StrictDataApiFake(fresh_db), FakeAuthBackend(FakeClock(datetime(2026, 10, 26, tzinfo=UTC)))
    idp.create_user("owner@example.com", "Owner")
    ensure_bootstrap(db, idp, EMAIL)
    assert (
        _users(db)["owner@example.com"]["status"] == "active" and idp.invites_sent("owner@example.com") == 0
    )


def test_custom_resource_runs_on_create_and_update_only(
    fresh_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL", EMAIL)
    db, idp = StrictDataApiFake(fresh_db), FakeAuthBackend(FakeClock(datetime(2026, 10, 26, tzinfo=UTC)))
    res = handler({"RequestType": "Create", "ResourceProperties": {}}, None, idp=idp, db=db)
    assert res["PhysicalResourceId"] == "tasklane-bootstrap" and "owner@example.com" not in json.dumps(res)
    handler({"RequestType": "Delete", "PhysicalResourceId": "tasklane-bootstrap"}, None, idp=idp, db=db)
    assert _users(db)["owner@example.com"]["role"] == "admin"  # delete keeps the admin
