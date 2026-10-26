"""User profile (A16, P1 basic): name, title, phone, timezone. A blank timezone means the account default (A16)."""

from __future__ import annotations

from typing import Any

from tasklane.identity.account import Invalid, valid_timezone
from tasklane.platform.db import Db

FIELDS = {"name": 80, "title": 100, "phone": 40, "timezone": 64}


def get(db: Db, user_id: int) -> dict[str, Any]:
    r = db.query(
        """select u.id::text as id, u.email::text as email, u.name, u.title, u.phone, u.timezone, u.role,
                  coalesce(u.timezone, a.timezone) as effective_timezone
           from tl.users u cross join tl.account a where u.id = :id""",
        {"id": user_id},
    )[0]
    return dict(r)


def update(db: Db, user_id: int, body: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(body) - set(FIELDS))
    errors: dict[str, str] = {k: "not editable here" for k in unknown}
    if not body:
        errors["body"] = "name, title, phone or timezone"
    if "name" in body and (not isinstance(body["name"], str) or not 1 <= len(body["name"].strip()) <= 80):
        errors["name"] = "1-80 characters"
    for k in ("title", "phone"):
        v = body.get(k)
        if k in body and v is not None and (not isinstance(v, str) or len(v) > FIELDS[k]):
            errors[k] = f"up to {FIELDS[k]} characters"
    tz = body.get("timezone")
    if "timezone" in body and tz is not None and not valid_timezone(tz):
        errors["timezone"] = "an IANA timezone such as Asia/Kolkata, or null for the account default"
    if errors:
        raise Invalid(errors)
    db.execute(
        """update tl.users set
             name = case when :has_name then :name else name end,
             title = case when :has_title then :title else title end,
             phone = case when :has_phone then :phone else phone end,
             timezone = case when :has_tz then :tz else timezone end,
             updated_at = now()
           where id = :id""",
        {
            "id": user_id,
            "has_name": "name" in body,
            "name": str(body.get("name", "")).strip(),
            "has_title": "title" in body,
            "title": (body.get("title") or "").strip() or None,
            "has_phone": "phone" in body,
            "phone": (body.get("phone") or "").strip() or None,
            "has_tz": "timezone" in body,
            "tz": tz or None,
        },
    )
    return get(db, user_id)
