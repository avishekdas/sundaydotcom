"""Workspaces, members and the left nav (A2, A4, K2; arch 04 §4.2).

Visibility of a workspace: Admins all (K1.1); Open workspaces to every active user; Closed ones to their members.
A workspace a user cannot see still appears in the nav as a breadcrumb holding only the boards they were invited to
(K2.1). Boards always come from ``vis_boards`` (ADR-014). Membership, kind and state changes bump the global
``perm_epoch`` so cached PermissionSnapshots re-load (07 §7.2).
"""

from __future__ import annotations

import json
from typing import Any

from tasklane.identity.visibility import visibility_ctes
from tasklane.platform.db import Db, Json
from tasklane.workmgmt.positions import key_between, spread

RESTORE_DAYS = 30
KINDS = ("open", "closed")


class NotFound(LookupError):
    pass


class Forbidden(PermissionError):
    pass


class Conflict(ValueError):
    pass


class Gone(LookupError):
    pass


class Invalid(ValueError):
    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("invalid")
        self.fields = fields


def _with_vis(user_id: int, select: str) -> tuple[str, dict[str, Any]]:
    ctes, params = visibility_ctes(user_id)
    head = ",\n".join(f"{c.name} as ({c.sql})" for c in ctes)
    return f"with {head}\n{select}", dict(params)


_WS_VISIBLE = """(vu.role = 'admin' or w.kind = 'open'
                  or exists (select 1 from tl.workspace_members m where m.workspace_id = w.id and m.user_id = vu.id))"""


def nav(db: Db, user_id: int) -> dict[str, Any]:
    sql, params = _with_vis(
        user_id,
        NAV_SELECT,
    )
    return {"workspaces": json.loads(db.query(sql, params)[0]["doc"])}


NAV_SELECT = """select coalesce(json_agg(x.doc order by x.position, x.id), '[]')::text as doc from (
              select w.id, w.position, json_build_object(
                'id', w.id::text, 'name', w.name, 'kind', w.kind, 'is_default', w.is_default,
                'breadcrumb_only', not __WS_VISIBLE__,
                'boards', coalesce((select json_agg(json_build_object('id', b.id::text, 'name', b.name)
                                                    order by b.position, b.id)
                                    from tl.boards b
                                    where b.workspace_id = w.id and b.parent_board_id is null
                                      and b.id in (select id from vis_boards)), '[]')) as doc
              from tl.workspaces w cross join vis_user vu
              where w.state = 'active'
                and (__WS_VISIBLE__
                     or exists (select 1 from tl.boards b where b.workspace_id = w.id
                                and b.id in (select id from vis_boards)))) x""".replace(
    "__WS_VISIBLE__", _WS_VISIBLE
)

ACCESS_SELECT = """select w.id::text as id, w.name, w.description, w.kind, w.is_default, w.state,
                   (w.deleted_at > now() - make_interval(days => :days::int)) as restorable,
                   (select m.role from tl.workspace_members m where m.workspace_id = w.id and m.user_id = vu.id) as my_role,
                   vu.role as user_role
            from tl.workspaces w
            cross join (select u.id, u.role from tl.users u where u.id = :uid and u.status = 'active') vu
            where w.id = :ws and __WS_VISIBLE__""".replace("__WS_VISIBLE__", _WS_VISIBLE)


def _access(db: Db, user_id: int, ws_id: int, *, include_deleted: bool = False) -> dict[str, Any]:
    """The workspace as the caller sees it, with ``my_role`` (owner | member | None) and ``owner_rights``."""
    rows = db.query(ACCESS_SELECT, {"uid": user_id, "ws": ws_id, "days": RESTORE_DAYS})
    if not rows or (rows[0]["state"] != "active" and not include_deleted):
        raise NotFound(str(ws_id))
    r = dict(rows[0])
    r["owner_rights"] = r["user_role"] == "admin" or r["my_role"] == "owner"
    return r


def _require_owner(db: Db, user_id: int, ws_id: int, *, include_deleted: bool = False) -> dict[str, Any]:
    ws = _access(db, user_id, ws_id, include_deleted=include_deleted)
    if not ws["owner_rights"]:
        raise Forbidden(str(ws_id))
    return ws


def _bump_epoch(db: Db) -> None:
    db.query("select tl.bump_perm_epoch() as epoch")


def _validate(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    if "name" in body or not partial:
        name = body.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            errors["name"] = "1-60 characters"
        else:
            out["name"] = name.strip()
    if "kind" in body or not partial:
        kind = body.get("kind", "open")
        if kind not in KINDS:
            errors["kind"] = "open or closed"
        else:
            out["kind"] = kind
    if "description" in body:
        d = body["description"]
        if d is not None and (not isinstance(d, str) or len(d) > 5000):
            errors["description"] = "text up to 5,000 characters"
        else:
            out["description"] = d
    if errors:
        raise Invalid(errors)
    if partial and not out:
        raise Invalid({"body": "nothing to change"})
    return out


def create(db: Db, user_id: int, body: dict[str, Any]) -> dict[str, Any]:
    f = _validate(body, partial=False)
    last = db.query("select max(position) as p from tl.workspaces")[0]["p"]
    rows = db.query(
        """with w as (insert into tl.workspaces (name, description, kind, position)
                      values (:name, :descr, :kind, :pos) returning id, name, kind),
                m as (insert into tl.workspace_members (workspace_id, user_id, role)
                      select id, :uid, 'owner' from w returning workspace_id)
           select w.id::text as id, w.name, w.kind from w""",
        {
            "name": f["name"],
            "descr": f.get("description"),
            "kind": f["kind"],
            "uid": user_id,
            "pos": key_between(last, None),
        },
    )
    return {**rows[0], "my_role": "owner"}


def get(db: Db, user_id: int, ws_id: int) -> dict[str, Any]:
    ws = _access(db, user_id, ws_id)
    members = db.query(
        """select m.user_id::text as user_id, m.role, u.name from tl.workspace_members m
           join tl.users u on u.id = m.user_id where m.workspace_id = :ws order by m.role desc, u.name""",
        {"ws": ws_id},
    )
    keys = ("id", "name", "description", "kind", "is_default", "my_role")
    return {**{k: ws[k] for k in keys}, "members": [dict(m) for m in members]}


def update(db: Db, user_id: int, ws_id: int, body: dict[str, Any]) -> dict[str, Any]:
    ws = _require_owner(db, user_id, ws_id)
    f = _validate(body, partial=True)
    db.execute(
        """update tl.workspaces set name = coalesce(:name, name), kind = coalesce(:kind, kind),
                  description = case when :has_descr then :descr else description end, version = version + 1
           where id = :ws""",
        {
            "name": f.get("name"),
            "kind": f.get("kind"),
            "has_descr": "description" in f,
            "descr": f.get("description"),
            "ws": ws_id,
        },
    )
    if f.get("kind") and f["kind"] != ws["kind"]:
        _bump_epoch(db)
    return get(db, user_id, ws_id)


def _owners(db: Db, ws_id: int) -> int:
    return int(
        db.query(
            "select count(*)::int as n from tl.workspace_members where workspace_id = :ws and role = 'owner'",
            {"ws": ws_id},
        )[0]["n"]
    )


def _role_of(db: Db, ws_id: int, user_id: int) -> str | None:
    rows = db.query(
        "select role from tl.workspace_members where workspace_id = :ws and user_id = :u",
        {"ws": ws_id, "u": user_id},
    )
    return str(rows[0]["role"]) if rows else None


def put_member(db: Db, user_id: int, ws_id: int, target: int, role: Any) -> None:
    _require_owner(db, user_id, ws_id)
    if role not in ("owner", "member"):
        raise Invalid({"role": "owner or member"})
    if not db.query("select 1 as x from tl.users where id = :u and status = 'active'", {"u": target}):
        raise Invalid({"user_id": "unknown or inactive user"})
    if role == "member" and _role_of(db, ws_id, target) == "owner" and _owners(db, ws_id) <= 1:
        raise Conflict("a workspace needs at least one owner")  # A2.2
    db.execute(
        """insert into tl.workspace_members (workspace_id, user_id, role) values (:ws, :u, :r)
           on conflict (workspace_id, user_id) do update set role = excluded.role""",
        {"ws": ws_id, "u": target, "r": role},
    )
    _bump_epoch(db)


def remove_member(db: Db, user_id: int, ws_id: int, target: int) -> None:
    ws = _access(db, user_id, ws_id)
    if target != user_id and not ws["owner_rights"]:
        raise Forbidden(str(ws_id))
    if target == user_id and ws["my_role"] is None and not ws["owner_rights"]:
        raise Forbidden(str(ws_id))
    if _role_of(db, ws_id, target) == "owner" and _owners(db, ws_id) <= 1:
        raise Conflict("a workspace needs at least one owner")  # A2.2
    db.execute(
        "delete from tl.workspace_members where workspace_id = :ws and user_id = :u",
        {"ws": ws_id, "u": target},
    )
    _bump_epoch(db)


def delete(db: Db, user_id: int, ws_id: int) -> None:
    ws = _require_owner(db, user_id, ws_id)
    if ws["is_default"]:
        raise Conflict("the default workspace cannot be deleted")  # A2.3
    db.execute(
        "update tl.workspaces set state = 'deleted', deleted_at = now(), version = version + 1 where id = :ws",
        {"ws": ws_id},
    )
    _bump_epoch(db)


def restore(db: Db, user_id: int, ws_id: int) -> dict[str, Any]:
    ws = _require_owner(db, user_id, ws_id, include_deleted=True)
    if ws["state"] == "deleted":
        if not ws["restorable"]:
            raise Gone(str(ws_id))  # purged by the trash job (A11.2, M9)
        db.execute(
            "update tl.workspaces set state = 'active', deleted_at = null, version = version + 1 where id = :ws",
            {"ws": ws_id},
        )
        _bump_epoch(db)
    return get(db, user_id, ws_id)


def move_board(db: Db, user_id: int, board_id: int, before_id: int | None) -> None:
    """A4.2: one shared order per workspace; ``before_id`` None moves the board to the end."""
    sql, params = _with_vis(
        user_id,
        """select b.id::text as id, b.position from tl.boards b
           where b.workspace_id = (select workspace_id from tl.boards where id = :b)
             and b.parent_board_id is null and b.state = 'active' and b.id in (select id from vis_boards)
           order by b.position, b.id""",
    )
    siblings = db.query(sql, {**params, "b": board_id})
    ids = [int(r["id"]) for r in siblings]
    if board_id not in ids:
        raise NotFound(str(board_id))
    if before_id is not None and (before_id == board_id or before_id not in ids):
        raise Invalid({"before_id": "a board of the same workspace"})
    keys = [str(r["position"]) for r in siblings]
    if len(set(keys)) != len(keys) or any(not k or k.endswith("0") for k in keys):
        keys = spread(len(ids))  # legacy or colliding keys: renumber once, in the same order
        db.execute(
            """update tl.boards b set position = x.p
               from jsonb_to_recordset(:rows::jsonb) as x(id bigint, p text) where b.id = x.id""",
            {"rows": Json([{"id": i, "p": k} for i, k in zip(ids, keys, strict=True)])},
        )
    order = [(i, k) for i, k in zip(ids, keys, strict=True) if i != board_id]
    if before_id is None:
        new = key_between(order[-1][1] if order else None, None)
    else:
        idx = next(n for n, (i, _) in enumerate(order) if i == before_id)
        new = key_between(order[idx - 1][1] if idx else None, order[idx][1])
    db.execute(
        "update tl.boards set position = :p, version = version + 1 where id = :b", {"p": new, "b": board_id}
    )
