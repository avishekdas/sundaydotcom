"""Account settings (A1.2): one row, Admin-only edits; the display subset is readable by every active user (A1.3)."""

from __future__ import annotations

import json
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tasklane.platform.db import Db, Json

DATE_FORMATS = ("DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD")
WEEK_STARTS = {"Sun": 0, "Mon": 1}
_DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class Invalid(ValueError):
    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("invalid")
        self.fields = fields


def settings(db: Db) -> dict[str, Any]:
    r = db.query(
        "select name, timezone, date_format, week_start::int as week_start, allowed_domains::text as domains "
        "from tl.account where id = 1"
    )[0]
    week = next(k for k, v in WEEK_STARTS.items() if v == int(r["week_start"]))
    return {
        "name": r["name"],
        "timezone": r["timezone"],
        "date_format": r["date_format"],
        "week_start": week,
        "allowed_domains": json.loads(r["domains"]),
    }


def display(db: Db) -> dict[str, Any]:
    s = settings(db)
    return {k: s[k] for k in ("name", "timezone", "date_format", "week_start")}


def valid_timezone(tz: Any) -> bool:
    if not isinstance(tz, str) or not tz or ("/" not in tz and tz != "UTC"):
        return False
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def update(db: Db, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Returns the new settings and the changes ``{field: {from, to}}`` (for the audit store)."""
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    if "name" in body:
        name = body["name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            errors["name"] = "1-80 characters"
        else:
            out["name"] = name.strip()
    if "timezone" in body:
        if not valid_timezone(body["timezone"]):
            errors["timezone"] = "an IANA timezone such as America/New_York"
        else:
            out["timezone"] = body["timezone"]
    if "date_format" in body:
        if body["date_format"] not in DATE_FORMATS:
            errors["date_format"] = "one of " + ", ".join(DATE_FORMATS)
        else:
            out["date_format"] = body["date_format"]
    if "week_start" in body:
        if body["week_start"] not in WEEK_STARTS:
            errors["week_start"] = "Sun or Mon"
        else:
            out["week_start"] = body["week_start"]
    if "allowed_domains" in body:
        doms = body["allowed_domains"]
        if not isinstance(doms, list) or not all(isinstance(d, str) for d in doms):
            errors["allowed_domains"] = "a list of domains"
        else:
            norm = list(dict.fromkeys(d.strip().lower() for d in doms if d.strip()))
            bad = [d for d in norm if not _DOMAIN.match(d)]
            if bad:
                errors["allowed_domains"] = "not a domain: " + ", ".join(bad)
            else:
                out["allowed_domains"] = norm
    if errors:
        raise Invalid(errors)
    if not out:
        raise Invalid({"body": "nothing to change"})
    before = settings(db)
    db.execute(
        """update tl.account set name = coalesce(:name, name), timezone = coalesce(:tz, timezone),
                  date_format = coalesce(:df, date_format), week_start = coalesce(:ws::smallint, week_start),
                  allowed_domains = coalesce(:doms::jsonb, allowed_domains)
           where id = 1""",
        {
            "name": out.get("name"),
            "tz": out.get("timezone"),
            "df": out.get("date_format"),
            "ws": WEEK_STARTS.get(out.get("week_start", "")),
            "doms": Json(out["allowed_domains"]) if "allowed_domains" in out else None,
        },
    )
    after = settings(db)
    changes = {k: {"from": before[k], "to": after[k]} for k in out if before[k] != after[k]}
    return after, changes


def allowed_domains(db: Db) -> list[str]:
    return list(
        json.loads(db.query("select allowed_domains::text as d from tl.account where id = 1")[0]["d"])
    )
