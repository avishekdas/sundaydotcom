"""Board access (B2, B3, K3 sets): owners and Admins manage kind, permission set and members; the last owner stays
(AC-B3-1). Every change bumps perm_epoch (07 §7.2). Self-unsubscribe (B3.2) comes with notifications (M3)."""

from __future__ import annotations

import pytest

from tasklane.api.app import Deps
from tests.integration.world import IDS, add_users, call, make_deps

pytestmark = pytest.mark.integration


@pytest.fixture
def deps(board_db: str) -> Deps:
    add_users(board_db)
    d = make_deps(board_db)
    d.db.execute(
        "insert into tl.boards (id, workspace_id, name, kind, position) values (90, 1, 'Deals', 'private', 'm')"
    )
    d.db.execute("insert into tl.board_members (board_id, principal_id, role) values (90, 44, 'owner')")
    return d


def _epoch(deps: Deps) -> int:
    return int(deps.db.query("select perm_epoch::text as e from tl.account")[0]["e"])


def test_owner_reads_and_changes_board_settings(deps: Deps) -> None:
    status, b = call(deps, "mia", "GET", "/api/v1/boards/90")
    assert status == 200 and b["kind"] == "private" and b["permission_set"] == "edit_everything"
    assert b["members"] == [{"user_id": str(IDS["mia"]), "name": "Mia", "role": "owner", "subscribed": True}]
    before = _epoch(deps)
    status, b = call(
        deps, "mia", "PATCH", "/api/v1/boards/90", {"permission_set": "view_comment", "kind": "main"}
    )
    assert status == 200 and b["permission_set"] == "view_comment" and b["kind"] == "main"
    assert _epoch(deps) > before
    assert call(deps, "raj", "GET", "/api/v1/boards/90/schema")[1]["capabilities"] == [
        "log_activities",
        "post_updates",
        "read",
    ]


@pytest.mark.parametrize(
    "body", [{"kind": "shareable"}, {"permission_set": "edit_assigned"}, {"permission_set": "x"}, {}]
)
def test_settings_are_validated(deps: Deps, body: dict[str, str]) -> None:
    """Shareable boards (guests) and edit_assigned (item guard) arrive later (P2, M2)."""
    assert call(deps, "mia", "PATCH", "/api/v1/boards/90", body)[0] == 400


def test_non_owners_cannot_change_access(deps: Deps) -> None:
    assert call(deps, "raj", "PATCH", "/api/v1/boards/90", {"kind": "main"})[0] == 404  # cannot even see it
    deps.db.execute("update tl.boards set kind = 'main' where id = 90")
    deps.snapshots.clear()
    assert (
        call(deps, "raj", "PATCH", "/api/v1/boards/90", {"kind": "private"})[0] == 403
    )  # sees it, not owner
    assert call(deps, "raj", "PUT", f"/api/v1/boards/90/members/{IDS['raj']}", {"role": "owner"})[0] == 403
    assert (
        call(deps, "ada", "PATCH", "/api/v1/boards/90", {"kind": "private"})[0] == 200
    )  # admin = owner rights


def test_owner_invites_a_member_who_then_sees_the_private_board(deps: Deps) -> None:
    assert call(deps, "raj", "GET", "/api/v1/boards/90/schema")[0] == 404
    assert call(deps, "mia", "PUT", f"/api/v1/boards/90/members/{IDS['raj']}", {"role": "member"})[0] == 200
    assert call(deps, "raj", "GET", "/api/v1/boards/90/schema")[0] == 200  # epoch bump → fresh snapshot
    assert call(deps, "mia", "DELETE", f"/api/v1/boards/90/members/{IDS['raj']}")[0] == 204
    assert call(deps, "raj", "GET", "/api/v1/boards/90/schema")[0] == 404


@pytest.mark.ac("AC-B3-1")
def test_last_owner_cannot_leave_or_be_demoted(deps: Deps) -> None:
    path = f"/api/v1/boards/90/members/{IDS['mia']}"
    assert call(deps, "mia", "DELETE", path)[0] == 409
    assert call(deps, "mia", "PUT", path, {"role": "member"})[0] == 409
    call(deps, "mia", "PUT", f"/api/v1/boards/90/members/{IDS['raj']}", {"role": "owner"})
    assert call(deps, "mia", "DELETE", path)[0] == 204


def test_member_validation(deps: Deps) -> None:
    assert call(deps, "mia", "PUT", f"/api/v1/boards/90/members/{IDS['raj']}", {"role": "boss"})[0] == 400
    assert call(deps, "mia", "PUT", "/api/v1/boards/90/members/999999", {"role": "member"})[0] == 400
