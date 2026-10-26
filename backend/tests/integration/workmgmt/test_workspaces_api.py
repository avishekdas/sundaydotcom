"""Workspaces, members and the left nav (A2, A4, K2; arch 04 §4.2 `GET /nav`, `/workspaces`).

World (board_db + world.add_users): workspace 1 "Main" (open, default) with main boards 10 and 20; Ada admin, Mia and
Raj members, Vic viewer. Membership and kind changes bump `perm_epoch` (07 §7.2) so cached snapshots re-load.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import psycopg
import pytest

from tasklane.api.app import Deps
from tests.integration.world import IDS, add_users, call, make_deps

pytestmark = pytest.mark.integration


@pytest.fixture
def deps(board_db: str) -> Deps:
    add_users(board_db)
    with psycopg.connect(board_db, autocommit=True) as c:
        c.execute("update tl.workspaces set is_default = true, name = 'Main workspace' where id = 1")
    return make_deps(board_db)


def nav(deps: Deps, who: str) -> dict[str, Any]:
    status, body = call(deps, who, "GET", "/api/v1/nav")
    assert status == 200
    return {w["name"]: w for w in body["workspaces"]}


def _epoch(deps: Deps) -> int:
    return int(deps.db.query("select perm_epoch::text as e from tl.account")[0]["e"])


def test_member_creates_a_workspace_and_owns_it(deps: Deps) -> None:
    status, ws = call(deps, "mia", "POST", "/api/v1/workspaces", {"name": "Sales", "kind": "open"})
    assert status == 201 and ws["name"] == "Sales" and ws["kind"] == "open" and ws["my_role"] == "owner"
    assert "Sales" in nav(deps, "mia") and "Sales" in nav(deps, "raj")  # open → everyone sees it


@pytest.mark.ac("AC-K1-1")
def test_viewer_cannot_create_a_workspace(deps: Deps) -> None:
    assert call(deps, "vic", "POST", "/api/v1/workspaces", {"name": "Nope", "kind": "open"})[0] == 403


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "x" * 61}, {"name": "ok", "kind": "secret"}])
def test_workspace_body_is_validated(deps: Deps, body: dict[str, Any]) -> None:
    assert call(deps, "mia", "POST", "/api/v1/workspaces", body)[0] == 400


@pytest.mark.ac("AC-A2-1")
@pytest.mark.ac("AC-K2-2")
def test_closed_workspace_and_its_boards_are_invisible_to_non_members(deps: Deps) -> None:
    ws = call(deps, "mia", "POST", "/api/v1/workspaces", {"name": "Board room", "kind": "closed"})[1]
    deps.db.execute(
        "insert into tl.boards (id, workspace_id, name, kind, position) values (60, :w, 'Plans', 'main', 'a')",
        {"w": int(ws["id"])},
    )
    assert "Board room" not in nav(deps, "raj")
    assert call(deps, "raj", "GET", f"/api/v1/workspaces/{ws['id']}")[0] == 404
    assert call(deps, "raj", "GET", "/api/v1/boards/60/schema")[0] == 404
    assert [b["name"] for b in nav(deps, "mia")["Board room"]["boards"]] == ["Plans"]
    assert "Board room" in nav(deps, "ada")  # admin override (K1.1)


@pytest.mark.ac("AC-K2-1")
def test_invite_to_a_private_board_shows_only_that_board_as_a_breadcrumb(deps: Deps) -> None:
    ws = call(deps, "mia", "POST", "/api/v1/workspaces", {"name": "Exec", "kind": "closed"})[1]
    deps.db.execute(
        "insert into tl.boards (id, workspace_id, name, kind, position) values "
        "(61, :w, 'Hiring', 'private', 'a'), (62, :w, 'Budget', 'main', 'b')",
        {"w": int(ws["id"])},
    )
    deps.db.execute("insert into tl.board_members (board_id, principal_id, role) values (61, 45, 'member')")
    exec_ws = nav(deps, "raj")["Exec"]
    assert exec_ws["breadcrumb_only"] is True
    assert [b["name"] for b in exec_ws["boards"]] == ["Hiring"]
    assert call(deps, "raj", "GET", "/api/v1/boards/61/schema")[0] == 200


@pytest.mark.ac("AC-A4-1")
def test_nav_hides_private_boards_without_access(deps: Deps) -> None:
    deps.db.execute(
        "insert into tl.boards (id, workspace_id, name, kind, position) values (63, 1, 'Secret', 'private', 'c')"
    )
    names = [b["name"] for b in nav(deps, "raj")["Main workspace"]["boards"]]
    assert "Secret" not in names and names == ["Board 10", "Board 20"]


def test_owner_manages_members_and_non_owners_cannot(deps: Deps) -> None:
    ws = call(deps, "mia", "POST", "/api/v1/workspaces", {"name": "Team", "kind": "closed"})[1]
    before = _epoch(deps)
    assert (
        call(deps, "raj", "PUT", f"/api/v1/workspaces/{ws['id']}/members/{IDS['vic']}", {"role": "member"})[0]
        == 404
    )
    assert (
        call(deps, "mia", "PUT", f"/api/v1/workspaces/{ws['id']}/members/{IDS['raj']}", {"role": "member"})[0]
        == 200
    )
    assert _epoch(deps) > before  # permission-relevant change (07 §7.2)
    assert "Team" in nav(deps, "raj")
    assert (
        call(deps, "raj", "PUT", f"/api/v1/workspaces/{ws['id']}/members/{IDS['vic']}", {"role": "member"})[0]
        == 403
    )
    members = call(deps, "mia", "GET", f"/api/v1/workspaces/{ws['id']}")[1]["members"]
    assert {(m["user_id"], m["role"]) for m in members} == {
        (str(IDS["mia"]), "owner"),
        (str(IDS["raj"]), "member"),
    }
    assert call(deps, "mia", "DELETE", f"/api/v1/workspaces/{ws['id']}/members/{IDS['raj']}")[0] == 204
    assert "Team" not in nav(deps, "raj")


@pytest.mark.ac("AC-A2-2")
def test_last_owner_cannot_leave_or_be_demoted(deps: Deps) -> None:
    ws = call(deps, "mia", "POST", "/api/v1/workspaces", {"name": "Solo", "kind": "open"})[1]
    path = f"/api/v1/workspaces/{ws['id']}/members/{IDS['mia']}"
    assert call(deps, "mia", "DELETE", path)[0] == 409
    assert call(deps, "mia", "PUT", path, {"role": "member"})[0] == 409
    call(deps, "mia", "PUT", f"/api/v1/workspaces/{ws['id']}/members/{IDS['raj']}", {"role": "owner"})
    assert call(deps, "mia", "DELETE", path)[0] == 204  # another owner remains


def test_owner_renames_and_changes_kind(deps: Deps) -> None:
    ws = call(deps, "mia", "POST", "/api/v1/workspaces", {"name": "Old", "kind": "open"})[1]
    assert call(deps, "raj", "PATCH", f"/api/v1/workspaces/{ws['id']}", {"name": "Hijack"})[0] == 403
    status, upd = call(
        deps, "mia", "PATCH", f"/api/v1/workspaces/{ws['id']}", {"name": "New", "kind": "closed"}
    )
    assert status == 200 and upd["name"] == "New" and upd["kind"] == "closed"
    assert "New" not in nav(deps, "raj")


@pytest.mark.ac("AC-A2-3")
def test_delete_and_restore_within_30_days_brings_boards_back(deps: Deps) -> None:
    ws = call(deps, "mia", "POST", "/api/v1/workspaces", {"name": "Temp", "kind": "open"})[1]
    for b in (70, 71, 72):
        deps.db.execute(
            "insert into tl.boards (id, workspace_id, name, kind, position) values (:b, :w, :n, 'main', :p)",
            {"b": b, "w": int(ws["id"]), "n": f"B{b}", "p": f"a{b}"},
        )
    assert call(deps, "raj", "DELETE", f"/api/v1/workspaces/{ws['id']}")[0] == 403
    assert call(deps, "mia", "DELETE", f"/api/v1/workspaces/{ws['id']}")[0] == 204
    assert "Temp" not in nav(deps, "mia")
    assert call(deps, "mia", "GET", "/api/v1/boards/70/schema")[0] == 404
    deps.clock.advance(days=29)  # type: ignore[attr-defined]
    deps.snapshots.clear()
    assert call(deps, "mia", "POST", f"/api/v1/workspaces/{ws['id']}/restore")[0] == 200
    assert [b["name"] for b in nav(deps, "mia")["Temp"]["boards"]] == ["B70", "B71", "B72"]


def test_restore_after_30_days_is_gone_and_default_workspace_cannot_be_deleted(deps: Deps) -> None:
    assert call(deps, "ada", "DELETE", "/api/v1/workspaces/1")[0] == 409  # A2.3
    ws = call(deps, "mia", "POST", "/api/v1/workspaces", {"name": "Old one", "kind": "open"})[1]
    call(deps, "mia", "DELETE", f"/api/v1/workspaces/{ws['id']}")
    deps.db.execute(
        "update tl.workspaces set deleted_at = deleted_at - :d::interval where id = :w",
        {"d": str(timedelta(days=31).days) + " days", "w": int(ws["id"])},
    )
    assert call(deps, "mia", "POST", f"/api/v1/workspaces/{ws['id']}/restore")[0] == 410


@pytest.mark.ac("AC-A4-2")
def test_board_reorder_persists_for_everyone(deps: Deps) -> None:
    deps.db.execute(
        "insert into tl.boards (id, workspace_id, name, kind, position) values (64, 1, 'Third', 'main', 'c')"
    )
    assert call(deps, "raj", "POST", "/api/v1/boards/64/move", {"before_id": "10"})[0] == 200
    assert [b["name"] for b in nav(deps, "mia")["Main workspace"]["boards"]] == [
        "Third",
        "Board 10",
        "Board 20",
    ]
    assert call(deps, "raj", "POST", "/api/v1/boards/10/move", {"before_id": None})[0] == 200  # to the end
    assert [b["name"] for b in nav(deps, "ada")["Main workspace"]["boards"]] == [
        "Third",
        "Board 20",
        "Board 10",
    ]
    assert call(deps, "vic", "POST", "/api/v1/boards/64/move", {"before_id": "20"})[0] == 403
    assert call(deps, "raj", "POST", "/api/v1/boards/64/move", {"before_id": "999"})[0] == 400
