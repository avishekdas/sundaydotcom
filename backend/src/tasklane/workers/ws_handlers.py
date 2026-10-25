"""WebSocket routes ($connect with ticket, $disconnect, subscribe) — API Gateway WebSocket API (ADR-005)."""

from __future__ import annotations

import json
import os
from functools import cache
from typing import Any

from tasklane.collab.realtime import DynamoRegistry, Registry
from tasklane.platform.aws_env import boto
from tasklane.platform.clock import SystemClock


@cache
def _registry() -> Registry:
    return DynamoRegistry(boto("dynamodb"), os.environ["REALTIME_TABLE"], SystemClock())


def handle(event: dict[str, Any], registry: Registry) -> dict[str, Any]:
    ctx = event["requestContext"]
    route, conn = ctx["routeKey"], ctx["connectionId"]
    if route == "$connect":
        ticket = (event.get("queryStringParameters") or {}).get("ticket", "")
        user = registry.redeem_ticket(ticket) if ticket else None
        if user is None:
            return {"statusCode": 401}
        registry.connect(conn, user)
        return {"statusCode": 200}
    if route == "$disconnect":
        registry.disconnect(conn)
        return {"statusCode": 200}
    if registry.user_of(conn) is None:
        return {"statusCode": 401}
    try:
        msg = json.loads(event.get("body") or "{}")
    except ValueError:
        return {"statusCode": 400}
    if msg.get("action") == "subscribe" and str(msg.get("board_id", "")).isdigit():
        registry.subscribe(conn, int(msg["board_id"]))  # board authorization arrives with M1 (VisibleItems)
        return {
            "statusCode": 200,
            "body": json.dumps({"type": "subscribed", "board_id": str(msg["board_id"])}),
        }
    if msg.get("action") == "ping":
        return {"statusCode": 200, "body": json.dumps({"type": "pong"})}
    return {"statusCode": 400}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle(event, _registry())
