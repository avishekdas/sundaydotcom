"""Board access (B2, B3, K3 sets): owners and Admins change the kind and permission set and manage members.

Kinds in P1: main | private (shareable needs guests, P2). Permission sets: edit_everything | edit_content |
view_comment (edit_assigned needs the M2 item guard). A board always keeps one owner (AC-B3-1). Every change bumps
``perm_epoch`` so snapshots and writes re-authorize (07 §7.2).
"""

from __future__ import annotations

from typing import Any

from tasklane.identity.snapshot import PermissionSnapshot
from tasklane.platform.db import Db
from tasklane.workmgmt.workspaces import Conflict, Forbidden, Invalid, NotFound

KINDS = ("main", "private")
SETS = ("edit_everything", "edit_content", "view_comment")


def _require_visible(snap: PermissionSnapshot, board_id: int) -> None:
    if snap.caps(board_id) is None:
        raise NotFound(str(board_id))


def _require_owner(snap: PermissionSnapshot, board_id: int) -> None:
    _require_visible(snap, board_id)
    if not (snap.role == "admin" or snap.boards[board_id].is_owner):
        raise Forbidden(str(board_id))


def get(db: Db, snap: PermissionSnapshot, board_id: int) -> dict[str, Any]:
    _require_visible(snap, board_id)
    b = db.query(
        "select id::text as id, name, kind, permission_set from tl.boards where id = :b and state = 'active'",
        {"b": board_id},
    )
    if not b:
        raise NotFound(str(board_id))
    members = db.query(
        """select m.principal_id::text as user_id, u.name, m.role, m.subscribed from tl.board_members m
           join tl.users u on u.id = m.principal_id
           where m.board_id = :b and m.principal_type = 'user' order by m.role desc, u.name""",
        {"b": board_id},
    )
    return {**dict(b[0]), "members": [dict(m) for m in members]}


def _bump(db: Db) -> None:
    db.query("select tl.bump_perm_epoch() as epoch")


def update(db: Db, snap: PermissionSnapshot, board_id: int, body: dict[str, Any]) -> dict[str, Any]:
    _require_owner(snap, board_id)
    errors: dict[str, str] = {}
    if "kind" in body and body["kind"] not in KINDS:
        errors["kind"] = "main or private"
    if "permission_set" in body and body["permission_set"] not in SETS:
        errors["permission_set"] = ", ".join(SETS)
    if not {"kind", "permission_set"} & set(body):
        errors["body"] = "kind or permission_set"
    if errors:
        raise Invalid(errors)
    db.execute(
        """update tl.boards set kind = coalesce(:k, kind), permission_set = coalesce(:p, permission_set),
                  version = version + 1 where id = :b""",
        {"k": body.get("kind"), "p": body.get("permission_set"), "b": board_id},
    )
    _bump(db)
    return get(db, snap, board_id)


def _owner_count(db: Db, board_id: int) -> int:
    return int(
        db.query(
            "select count(*)::int as n from tl.board_members where board_id = :b and principal_type = 'user' "
            "and role = 'owner'",
            {"b": board_id},
        )[0]["n"]
    )


def _role_of(db: Db, board_id: int, user_id: int) -> str | None:
    rows = db.query(
        "select role from tl.board_members where board_id = :b and principal_type = 'user' and principal_id = :u",
        {"b": board_id, "u": user_id},
    )
    return str(rows[0]["role"]) if rows else None


def put_member(db: Db, snap: PermissionSnapshot, board_id: int, user_id: int, role: Any) -> dict[str, Any]:
    _require_owner(snap, board_id)
    if role not in ("owner", "member"):
        raise Invalid({"role": "owner or member"})
    if not db.query("select 1 as x from tl.users where id = :u and status = 'active'", {"u": user_id}):
        raise Invalid({"user_id": "unknown or inactive user"})
    if role == "member" and _role_of(db, board_id, user_id) == "owner" and _owner_count(db, board_id) <= 1:
        raise Conflict("a board needs at least one owner")  # B3.1
    db.execute(
        """insert into tl.board_members (board_id, principal_type, principal_id, role) values (:b, 'user', :u, :r)
           on conflict (board_id, principal_type, principal_id) do update set role = excluded.role""",
        {"b": board_id, "u": user_id, "r": role},
    )
    _bump(db)
    return get(db, snap, board_id)


def remove_member(db: Db, snap: PermissionSnapshot, board_id: int, user_id: int) -> None:
    _require_owner(snap, board_id)
    if _role_of(db, board_id, user_id) == "owner" and _owner_count(db, board_id) <= 1:
        raise Conflict("a board needs at least one owner")  # AC-B3-1
    db.execute(
        "delete from tl.board_members where board_id = :b and principal_type = 'user' and principal_id = :u",
        {"b": board_id, "u": user_id},
    )
    _bump(db)
