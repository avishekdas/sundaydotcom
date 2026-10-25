"""scheduler-tick (PE-10): once a minute — partitions ahead, retention drops (more duties join later)."""

from __future__ import annotations

from typing import Any

from tasklane.platform.db import Db

RETENTION_DAYS = {"tl.board_changes": 2, "tl.outbox": 7, "tl.activity_log": 365}


def tick(db: Db) -> dict[str, Any]:
    created = 0
    for parent in ("tl.board_changes", "tl.outbox"):
        rows = db.query(
            "select tl.ensure_partitions(:p::regclass, current_date - 1, 9, 'day') as n", {"p": parent}
        )
        created += int(rows[0]["n"])
    rows = db.query("select tl.ensure_partitions('tl.activity_log'::regclass, current_date, 3, 'month') as n")
    created += int(rows[0]["n"])
    dropped = 0
    for parent, keep in RETENTION_DAYS.items():
        rows = db.query(
            "select tl.drop_partitions_older_than(:p::regclass, :k) as n", {"p": parent, "k": keep}
        )
        dropped += int(rows[0]["n"])
    return {"created": created, "dropped": dropped}
