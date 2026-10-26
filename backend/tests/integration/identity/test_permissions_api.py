"""Permission framework wired into the API (arch 07 §7.2, ADR-008): PermissionSnapshot from one SQL statement,
cached ≤ 30 s, epoch-guarded writes, tokens_valid_after, 404 for invisible boards, 403 for missing capabilities."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from tasklane.api.app import Deps, handle, reset_permission_cache
from tasklane.collab.realtime import InMemoryRegistry
from tasklane.platform.clock import FakeClock
from tasklane.platform.db import StrictDataApiFake

pytestmark = pytest.mark.integration
SUBS = {
    "ada": "00000000-0000-0000-0000-000000000042",  # admin (board_db)
    "mia": "00000000-0000-0000-0000-000000000044",  # member, owner of board 30
    "raj": "00000000-0000-0000-0000-000000000045",  # member
    "vic": "00000000-0000-0000-0000-000000000043",  # viewer
}
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


class _NoPublish:
    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        return []


@pytest.fixture
def deps(board_db: str) -> Deps:
    with psycopg.connect(board_db, autocommit=True) as c:
        c.execute(
            "insert into tl.users (id, email, name, role, status, cognito_sub) values "
            "(43, 'v@example.com', 'Vic', 'viewer', 'active', %s), (44, 'm@example.com', 'Mia', 'member', 'active', %s),"
            " (45, 'r@example.com', 'Raj', 'member', 'active', %s)",
            (SUBS["vic"], SUBS["mia"], SUBS["raj"]),
        )
        c.execute("update tl.boards set permission_set = 'edit_content' where id = 20")
        c.execute(
            "insert into tl.boards (id, workspace_id, name, kind, position, permission_set) values "
            "(30, 1, 'Private', 'private', 'b', 'edit_everything')"
        )
        c.execute("insert into tl.board_members (board_id, principal_id, role) values (30, 44, 'owner')")
        c.execute(
            "insert into tl.groups (id, board_id, title, color, position) values (300, 30, 'G', 'blue', 'a')"
        )
        c.execute(
            "insert into tl.columns (board_id, id, title, type, settings, position) values "
            "(20, 'note', 'Note', 'text', '{}', 'a'), (30, 'note', 'Note', 'text', '{}', 'a')"
        )
        c.execute(
            "insert into tl.items (id, board_id, group_id, name, position, created_by_type) values "
            "(3001, 30, 300, 'Secret', 'a', 'user')"
        )
    reset_permission_cache()
    clock = FakeClock(NOW)
    return Deps(
        db=StrictDataApiFake(board_db),
        publisher=_NoPublish(),
        registry=InMemoryRegistry(clock),
        clock=clock,
        ws_url="/ws",
        bus_name="t",
    )


def call(
    deps: Deps, who: str, method: str, path: str, body: Any = None, *, iat: int | None = None
) -> tuple[int, Any]:
    claims: dict[str, Any] = {"sub": SUBS[who], "iat": str(iat if iat is not None else int(NOW.timestamp()))}
    ev = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "http": {"method": method, "path": path, "sourceIp": "1.1.1.1"},
            "requestId": "r",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": claims}},
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }
    res = handle(ev, deps)
    return res["statusCode"], json.loads(res["body"]) if res.get("body") else None


@pytest.mark.ac("AC-B2-1")
def test_private_board_is_404_for_a_non_invited_member(deps: Deps) -> None:
    assert call(deps, "raj", "GET", "/api/v1/boards/30/schema")[0] == 404
    assert call(deps, "raj", "POST", "/api/v1/boards/30/query", {})[0] == 404
    assert call(deps, "raj", "PATCH", "/api/v1/items/3001/values", {"values": {"note": "x"}})[0] == 404
    assert call(deps, "mia", "GET", "/api/v1/boards/30/schema")[0] == 200  # owner
    assert call(deps, "ada", "GET", "/api/v1/boards/30/schema")[0] == 200  # admin override (K1.1)


@pytest.mark.ac("AC-K3-3")
def test_viewer_cannot_edit_on_an_edit_everything_board(deps: Deps) -> None:
    status, body = call(deps, "vic", "PATCH", "/api/v1/items/1001/values", {"values": {"note": "x"}})
    assert status == 403 and body["error"]["code"] == "forbidden"
    assert call(deps, "raj", "PATCH", "/api/v1/items/1001/values", {"values": {"note": "x"}})[0] == 200


@pytest.mark.ac("AC-K3-2")
def test_only_edit_content_refuses_structure(deps: Deps) -> None:
    assert call(deps, "raj", "POST", "/api/v1/boards/20/columns", {"title": "Priority"})[0] == 403
    schema = call(deps, "raj", "GET", "/api/v1/boards/20/schema")[1]
    assert (
        "edit_structure" not in schema["capabilities"] and "edit_values" in schema["capabilities"]
    )  # UI hides "+"
    status, col = call(deps, "raj", "POST", "/api/v1/boards/10/columns", {"title": "Priority"})
    assert status == 201 and col["type"] == "text" and col["title"] == "Priority"
    assert any(
        c["id"] == col["id"] for c in call(deps, "raj", "GET", "/api/v1/boards/10/schema")[1]["columns"]
    )


def test_column_create_validates_and_rejects_duplicate_titles(deps: Deps) -> None:
    assert call(deps, "ada", "POST", "/api/v1/boards/10/columns", {})[0] == 400
    assert call(deps, "ada", "POST", "/api/v1/boards/10/columns", {"title": "x" * 61})[0] == 400
    assert call(deps, "ada", "POST", "/api/v1/boards/10/columns", {"title": "Owner"})[0] == 201
    assert call(deps, "ada", "POST", "/api/v1/boards/10/columns", {"title": "owner"})[0] == 409


def test_tokens_issued_before_tokens_valid_after_are_refused(deps: Deps) -> None:
    deps.db.execute(
        "update tl.users set tokens_valid_after = :t::timestamptz where id = 45", {"t": NOW.isoformat()}
    )
    reset_permission_cache()
    assert call(deps, "raj", "GET", "/api/v1/me", iat=int(NOW.timestamp()) - 1)[0] == 401
    assert call(deps, "raj", "GET", "/api/v1/me", iat=int(NOW.timestamp()))[0] == 200


def test_demotion_applies_to_the_next_write_through_the_epoch_guard(deps: Deps) -> None:
    """F7.7: a cached snapshot never authorizes a write after the epoch moved (SEC-3, FR-9 re-authorize once)."""
    assert call(deps, "raj", "PATCH", "/api/v1/items/1001/values", {"values": {"note": "a"}})[0] == 200
    deps.db.execute("update tl.users set role = 'viewer' where id = 45")
    deps.db.execute("update tl.account set perm_epoch = perm_epoch + 1")
    assert call(deps, "raj", "PATCH", "/api/v1/items/1001/values", {"values": {"note": "b"}})[0] == 403


def test_snapshot_is_cached_for_at_most_30_seconds(deps: Deps) -> None:
    assert call(deps, "raj", "GET", "/api/v1/boards/30/schema")[0] == 404
    deps.db.execute("insert into tl.board_members (board_id, principal_id, role) values (30, 45, 'member')")
    assert deps.clock is not None
    deps.clock.advance(seconds=31)  # type: ignore[attr-defined]
    assert call(deps, "raj", "GET", "/api/v1/boards/30/schema")[0] == 200


def test_me_reports_role_and_account_capabilities(deps: Deps) -> None:
    status, me = call(deps, "vic", "GET", "/api/v1/me")
    assert status == 200 and me["role"] == "viewer" and me["capabilities"] == []
    assert "create_workspace" in call(deps, "raj", "GET", "/api/v1/me")[1]["capabilities"]


# --- AC-K3-4: generated permission matrix over the route inventory -------------------------------------------------
# Every authenticated route declares what it needs; a new route fails test_every_route_declares_its_capability
# until it is added here, so the matrix grows with the API (TP-13).
from tasklane.api.app import route_inventory  # noqa: E402
from tasklane.identity.authz import Cap, board_caps  # noqa: E402

BOARD_ROUTES: dict[tuple[str, str], Cap] = {
    ("GET", "/api/v1/boards/<board_id>/schema"): Cap.READ,
    ("POST", "/api/v1/boards/<board_id>/query"): Cap.READ,
    ("POST", "/api/v1/boards/<board_id>/items:fetch"): Cap.READ,
    ("POST", "/api/v1/boards/<board_id>/changes"): Cap.READ,
    ("POST", "/api/v1/boards/<board_id>/columns"): Cap.EDIT_STRUCTURE,
    ("PATCH", "/api/v1/items/<item_id>/values"): Cap.EDIT_VALUES,
}
WORKSPACE_ROUTES = {  # authorized by workspace role / account caps; behaviour in workmgmt/test_workspaces_api.py
    ("GET", "/api/v1/nav"),
    ("POST", "/api/v1/workspaces"),
    ("GET", "/api/v1/workspaces/<workspace_id>"),
    ("PATCH", "/api/v1/workspaces/<workspace_id>"),
    ("DELETE", "/api/v1/workspaces/<workspace_id>"),
    ("POST", "/api/v1/workspaces/<workspace_id>/restore"),
    ("PUT", "/api/v1/workspaces/<workspace_id>/members/<user_id>"),
    ("DELETE", "/api/v1/workspaces/<workspace_id>/members/<user_id>"),
    ("POST", "/api/v1/boards/<board_id>/move"),
}
ADMIN_ROUTES = {  # account administration (K1: Admin only); behaviour in identity/test_users_api.py
    ("GET", "/api/v1/users"),
    ("POST", "/api/v1/users"),
    ("PATCH", "/api/v1/users/<user_id>"),
    ("DELETE", "/api/v1/users/<user_id>"),
    ("POST", "/api/v1/users/<user_id>/resend-invite"),
}
SELF_ROUTES = {  # any active user, about themselves
    ("GET", "/api/v1/me"),
    ("POST", "/api/v1/realtime/ticket"),
    ("POST", "/api/v1/me/sign-out-everywhere"),
}
WORLD = {  # board id → (item on it, permission set, kind, owners)
    10: (1001, "edit_everything", "main", set()),
    20: (2001, "edit_content", "main", set()),
    30: (3001, "edit_everything", "private", {"mia"}),
}
ROLES = {"ada": "admin", "mia": "member", "raj": "member", "vic": "viewer"}


def test_every_route_declares_its_capability() -> None:
    authed = {r for r in route_inventory() if not r[1].startswith("/api/auth/")}
    assert authed == set(BOARD_ROUTES) | SELF_ROUTES | WORKSPACE_ROUTES | ADMIN_ROUTES


def _expected(who: str, board: int, cap: Cap) -> str:
    _item, pset, kind, owners = WORLD[board]
    visible = ROLES[who] == "admin" or kind == "main" or who in owners
    if not visible:
        return "404"
    return "ok" if cap in board_caps(ROLES[who], is_owner=who in owners, permission_set=pset) else "403"


@pytest.mark.ac("AC-K3-4")
@pytest.mark.parametrize("route", sorted(BOARD_ROUTES))
def test_permission_matrix(deps: Deps, route: tuple[str, str]) -> None:
    method, template = route
    got, want = {}, {}
    for who in ROLES:
        for board, (item, *_rest) in WORLD.items():
            path = template.replace("<board_id>", str(board)).replace("<item_id>", str(item))
            body: Any = {
                "PATCH": {"values": {"note": f"{who}-{board}"}},
                "GET": None,
            }.get(method, {})
            if template.endswith("/columns"):
                body = {"title": f"{who} col"}
            if template.endswith("items:fetch"):
                body = {"ids": [str(item)]}
            status = call(deps, who, method, path, body)[0]
            got[(who, board)] = "ok" if status in (200, 201) else str(status)
            want[(who, board)] = _expected(who, board, BOARD_ROUTES[route])
    assert got == want
