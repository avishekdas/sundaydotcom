"""Users, invites, roles and deactivation (F1, F2, K1; arch 07 §7.1 revocation; D-054).

Admin-only (the API checks ``manage_account``). Cognito holds credentials; ``tl.users`` holds role and status.
Role and status changes bump ``perm_epoch`` so cached snapshots and writes re-authorize (F7.7); deactivation also
disables the Cognito user, signs it out everywhere and moves ``tokens_valid_after`` (AC-F1-2).
"""

from __future__ import annotations

import re
from typing import Any

from tasklane.identity.idp import IdentityProvider, UserExists
from tasklane.platform.db import Db

ROLES = ("admin", "member", "viewer")  # guests arrive with shareable boards (P2)
STATUSES = ("active", "deactivated")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    pass


class Invalid(ValueError):
    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("invalid")
        self.fields = fields


def list_users(db: Db) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in db.query(
            "select id::text as id, email::text as email, name, role, status from tl.users order by lower(name), id"
        )
    ]


def _get(db: Db, user_id: int) -> dict[str, Any]:
    rows = db.query(
        "select id::text as id, email::text as email, name, role, status from tl.users where id = :id",
        {"id": user_id},
    )
    if not rows:
        raise NotFound(str(user_id))
    return dict(rows[0])


def _bump_epoch(db: Db) -> None:
    db.execute("update tl.account set perm_epoch = perm_epoch + 1")


def invite(db: Db, idp: IdentityProvider, body: dict[str, Any]) -> dict[str, Any]:
    email = str(body.get("email") or "").strip().lower()
    name = str(body.get("name") or "").strip()
    role = body.get("role")
    errors: dict[str, str] = {}
    if not _EMAIL.match(email) or len(email) > 254:
        errors["email"] = "a valid email address"
    if not 1 <= len(name) <= 120:
        errors["name"] = "1-120 characters"
    if role not in ROLES:
        errors["role"] = "admin, member or viewer"
    if errors:
        raise Invalid(errors)
    if db.query("select 1 as x from tl.users where email = :e", {"e": email}):
        raise Conflict("a user with this email already exists")
    try:
        sub = idp.invite(email, name)  # Cognito emails the temporary password (D-054)
    except UserExists:
        raise Conflict("a user with this email already exists") from None
    rows = db.query(
        "insert into tl.users (cognito_sub, email, name, role, status) values (:sub::uuid, :e, :n, :r, 'invited') "
        "returning id::text as id, email::text as email, name, role, status",
        {"sub": sub, "e": email, "n": name, "r": role},
    )
    return dict(rows[0])


def resend_invite(db: Db, idp: IdentityProvider, user_id: int) -> dict[str, Any]:
    user = _get(db, user_id)
    if user["status"] != "invited":
        raise Conflict("only pending invitations can be resent")
    idp.resend_invite(user["email"])
    return user


def revoke_invite(db: Db, idp: IdentityProvider, user_id: int) -> None:
    user = _get(db, user_id)
    if user["status"] != "invited":
        raise Conflict("active users are deactivated, not deleted (F1.3)")
    idp.delete_user(user["email"])
    db.execute("delete from tl.users where id = :id and status = 'invited'", {"id": user_id})


def _active_admins_other_than(db: Db, user_id: int) -> int:
    rows = db.query(
        "select count(*)::int as n from tl.users where role = 'admin' and status = 'active' and id <> :id",
        {"id": user_id},
    )
    return int(rows[0]["n"])


def update(db: Db, idp: IdentityProvider, user_id: int, body: dict[str, Any]) -> dict[str, Any]:
    user = _get(db, user_id)
    role, status = body.get("role"), body.get("status")
    errors: dict[str, str] = {}
    if role is not None and role not in ROLES:
        errors["role"] = "admin, member or viewer"
    if status is not None and status not in STATUSES:
        errors["status"] = "active or deactivated"
    if role is None and status is None:
        errors["body"] = "role or status"
    if errors:
        raise Invalid(errors)
    losing_admin = (
        user["role"] == "admin"
        and user["status"] == "active"
        and ((role is not None and role != "admin") or status == "deactivated")
    )
    if losing_admin and _active_admins_other_than(db, user_id) == 0:
        raise Conflict("the account needs at least one active admin (F1.4)")
    if status == "deactivated" and user["status"] != "deactivated":
        idp.disable(user["email"])
        idp.global_sign_out(user["email"])
        db.execute(
            "update tl.users set status = 'deactivated', tokens_valid_after = date_trunc('second', now()), "
            "updated_at = now() where id = :id",
            {"id": user_id},
        )
    elif status == "active" and user["status"] == "deactivated":
        idp.enable(user["email"])
        db.execute(
            "update tl.users set status = 'active', updated_at = now() where id = :id", {"id": user_id}
        )
    if role is not None and role != user["role"]:
        db.execute(
            "update tl.users set role = :r, updated_at = now() where id = :id", {"r": role, "id": user_id}
        )
    _bump_epoch(db)
    return _get(db, user_id)


def activate_invitee(db: Db, email: str) -> None:
    """The invitee set their password (F1.2): the account becomes usable."""
    db.execute(
        "update tl.users set status = 'active', updated_at = now() where email = :e and status = 'invited'",
        {"e": email.strip().lower()},
    )
