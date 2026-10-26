"""P1 audit store (A15.5, NFR-S6; K9 UI is P2). Rows are appended through the ``tl_audit_writer`` role only, so the
log cannot be edited or read back by the api role (07 §7.3, D-056). Event kinds follow 07 §7.4: admin override,
sign-in failures, role and permission changes, (de)activation, settings, password resets, sign-out everywhere."""

from __future__ import annotations

from typing import Any

from tasklane.platform.db import Db, Json


def record(
    db: Db,
    kind: str,
    *,
    actor_id: int | None,
    target: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    db.execute(
        "insert into tl.audit_events (actor_id, kind, target, ip, user_agent) "
        "values (:actor, :kind, :target::jsonb, :ip::inet, :ua)",
        {
            "actor": actor_id,
            "kind": kind,
            "target": Json(target or {}),
            "ip": ip,
            "ua": (user_agent or "")[:200],
        },
    )
