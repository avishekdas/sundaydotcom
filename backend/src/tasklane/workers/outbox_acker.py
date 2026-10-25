"""outbox-acker λ: SQS (EventBridge rule → outbox-ack queue) → mark published_at (arch 05 §5.1 step 3)."""

from __future__ import annotations

import json
from typing import Any

from tasklane.platform.clock import SystemClock
from tasklane.platform.outbox import ack
from tasklane.workers._env import db_from_env


def handler(event: dict[str, Any], context: Any, *, rds_client: Any = None) -> dict[str, Any]:
    ids: list[str] = []
    bad: list[dict[str, str]] = []
    for rec in event.get("Records", []):
        try:
            ids.append(str(json.loads(rec["body"])["detail"]["event_id"]))
        except (KeyError, TypeError, ValueError):
            bad.append({"itemIdentifier": rec.get("messageId", "")})
    if ids:
        ack(db_from_env(rds_client), ids, now=SystemClock().now())
    return {"batchItemFailures": bad}  # partial batch response: only malformed records go to the DLQ
