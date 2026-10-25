"""outbox-sweeper λ (every minute; reserved concurrency 1 + lease): republish unacked outbox rows."""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Any

from tasklane.platform.aws_env import boto, db_from_env
from tasklane.platform.clock import SystemClock
from tasklane.platform.outbox import EventBridgePublisher, sweep


def handler(
    event: dict[str, Any], context: Any, *, rds_client: Any = None, events_client: Any = None
) -> dict[str, Any]:
    report = sweep(
        db_from_env(rds_client),
        EventBridgePublisher(events_client or boto("events")),
        SystemClock(),
        holder=getattr(context, "aws_request_id", "local"),
        bus_name=os.environ["EVENT_BUS_NAME"],
        source="tasklane",
    )
    out = dataclasses.asdict(report)
    out["circuit_open"] = int(report.circuit_open)  # numeric for the metric filter
    print(json.dumps({"metric": "outbox.sweep", **out}))  # structured log → metric filters
    return out
