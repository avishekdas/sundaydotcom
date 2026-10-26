"""Account settings (A1) and the P1 audit store (A15.5, K1.1, 07 §7.4 event list; D-056).

Audit rows go through ``Deps.audit_db`` (the tl_audit_writer role in AWS); here it is the same database.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tasklane.api.app import Deps
from tasklane.identity.auth_backend import FakeAuthBackend
from tasklane.identity.auth_proxy import AuthProxy
from tasklane.platform.counters import InMemoryCounters
from tests.integration.world import IDS, add_users, call, make_deps

pytestmark = pytest.mark.integration


@pytest.fixture
def deps(board_db: str) -> Deps:
    add_users(board_db)
    _URI["db"] = board_db
    d = make_deps(board_db)
    cognito = FakeAuthBackend(d.clock)
    for email in ("a@example.com", "v@example.com", "m@example.com", "r@example.com"):
        cognito.add_user(email, "Existing-Password-1")
    d.idp = cognito
    d.auth = AuthProxy(cognito, InMemoryCounters(d.clock), d.clock, sleep=lambda s: None)
    return d


_URI: dict[str, str] = {}


def audit(deps: Deps, kind: str) -> list[dict[str, Any]]:
    from tasklane.platform.db import StrictDataApiFake

    rows = StrictDataApiFake(_URI["db"]).query(  # the api role cannot read the audit store
        "select actor_id::text as actor, target::text as target, host(ip) as ip from tl.audit_events "
        "where kind = :k order by id",
        {"k": kind},
    )
    return [{"actor": r["actor"], "target": json.loads(r["target"] or "null"), "ip": r["ip"]} for r in rows]


def test_everyone_reads_the_display_settings(deps: Deps) -> None:
    status, acct = call(deps, "vic", "GET", "/api/v1/account")
    assert status == 200 and set(acct) == {"name", "timezone", "date_format", "week_start"}


@pytest.mark.ac("AC-A1-1")
def test_admin_renames_the_account_and_it_is_audited(deps: Deps) -> None:
    status, settings = call(deps, "ada", "PATCH", "/api/v1/account/settings", {"name": "Acme Inc"})
    assert status == 200 and settings["name"] == "Acme Inc"
    assert call(deps, "raj", "GET", "/api/v1/account")[1]["name"] == "Acme Inc"  # top bar for all users
    [row] = audit(deps, "account.settings_changed")
    assert row["actor"] == str(IDS["ada"]) and row["target"]["changes"]["name"] == {
        "from": "Tasklane",
        "to": "Acme Inc",
    }


@pytest.mark.ac("AC-A1-2")
@pytest.mark.parametrize("who", ["mia", "vic"])
def test_settings_are_admin_only(deps: Deps, who: str) -> None:
    assert call(deps, who, "GET", "/api/v1/account/settings")[0] == 403
    assert call(deps, who, "PATCH", "/api/v1/account/settings", {"name": "Mine"})[0] == 403


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "x" * 81},
        {"timezone": "Mars/Base"},
        {"date_format": "DD.MM.YY"},
        {"week_start": "Tue"},
        {"allowed_domains": "acme.com"},
        {"allowed_domains": ["not a domain"]},
        {},
    ],
)
def test_settings_are_validated(deps: Deps, body: dict[str, Any]) -> None:
    assert call(deps, "ada", "PATCH", "/api/v1/account/settings", body)[0] == 400


def test_admin_reads_and_updates_every_setting(deps: Deps) -> None:
    body = {
        "timezone": "Asia/Kolkata",
        "date_format": "DD/MM/YYYY",
        "week_start": "Sun",
        "allowed_domains": ["Acme.com", "acme.co.uk"],
    }
    status, s = call(deps, "ada", "PATCH", "/api/v1/account/settings", body)
    assert status == 200
    assert s == {
        "name": "Tasklane",
        "timezone": "Asia/Kolkata",
        "date_format": "DD/MM/YYYY",
        "week_start": "Sun",
        "allowed_domains": ["acme.com", "acme.co.uk"],
    }
    assert call(deps, "ada", "GET", "/api/v1/account/settings")[1] == s


@pytest.mark.ac("AC-A1-3")
def test_invites_are_limited_to_allowed_domains(deps: Deps) -> None:
    call(deps, "ada", "PATCH", "/api/v1/account/settings", {"allowed_domains": ["acme.com"]})
    status, body = call(
        deps, "ada", "POST", "/api/v1/users", {"email": "bob@other.com", "name": "Bob", "role": "member"}
    )
    assert status == 400 and "acme.com" in body["error"]["fields"]["email"]
    assert (
        call(
            deps, "ada", "POST", "/api/v1/users", {"email": "sam@acme.com", "name": "Sam", "role": "member"}
        )[0]
        == 201
    )


@pytest.mark.ac("AC-K1-2")
def test_admin_override_on_a_private_board_is_audited(deps: Deps) -> None:
    deps.db.execute(
        "insert into tl.boards (id, workspace_id, name, kind, position) values (80, 1, 'HR', 'private', 'z')"
    )
    deps.db.execute("insert into tl.board_members (board_id, principal_id, role) values (80, 44, 'owner')")
    assert call(deps, "ada", "GET", "/api/v1/boards/80/schema")[0] == 200
    [row] = audit(deps, "admin.override_access")
    assert row["actor"] == str(IDS["ada"]) and row["target"] == {"board_id": "80"}
    assert call(deps, "mia", "GET", "/api/v1/boards/80/schema")[0] == 200  # owner: no override
    assert call(deps, "ada", "GET", "/api/v1/boards/10/schema")[0] == 200  # main board: no override
    assert len(audit(deps, "admin.override_access")) == 1


def test_user_administration_is_audited(deps: Deps) -> None:
    call(deps, "ada", "POST", "/api/v1/users", {"email": "new@example.com", "name": "New", "role": "viewer"})
    call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['raj']}", {"role": "viewer"})
    call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['raj']}", {"status": "deactivated"})
    call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['raj']}", {"status": "active"})
    assert audit(deps, "user.invited")[0]["target"]["email"] == "new@example.com"
    assert audit(deps, "user.role_changed")[0]["target"] == {
        "user_id": str(IDS["raj"]),
        "from": "member",
        "to": "viewer",
    }
    assert audit(deps, "user.deactivated")[0]["target"] == {"user_id": str(IDS["raj"])}
    assert audit(deps, "user.reactivated")[0]["target"] == {"user_id": str(IDS["raj"])}


def test_auth_events_are_audited_with_the_viewer_ip(deps: Deps) -> None:
    from tests.integration.api.test_auth_routes import call as raw_call

    raw_call(
        deps,
        "POST",
        "/api/auth/sign-in",
        {"email": "r@example.com", "password": "nope-nope-nope"},
        origin=None,
    )
    raw_call(
        deps,
        "POST",
        "/api/auth/sign-in",
        {"email": "ghost@example.com", "password": "nope-nope-nope"},
        origin=None,
    )
    fails = audit(deps, "auth.sign_in_failed")
    assert [f["target"]["email"] for f in fails] == ["r@example.com", "ghost@example.com"]
    assert fails[0]["ip"] == "203.0.113.1"
    call(deps, "raj", "POST", "/api/v1/me/sign-out-everywhere")
    assert audit(deps, "auth.sign_out_everywhere")[0]["actor"] == str(IDS["raj"])
