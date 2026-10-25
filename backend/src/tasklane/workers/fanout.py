"""fan-out λ: EventBridge (item.*) → post shaped messages to subscribed WebSocket connections."""

from __future__ import annotations

import os
from typing import Any

from tasklane.collab.realtime import ApiGatewayGateway, DynamoRegistry, fan_out
from tasklane.platform.clock import SystemClock


def handler(
    event: dict[str, Any], context: Any, *, registry: Any = None, gateway: Any = None
) -> dict[str, Any]:
    if registry is None or gateway is None:
        import boto3  # type: ignore[import-untyped]

        registry = registry or DynamoRegistry(
            boto3.client("dynamodb"), os.environ["REALTIME_TABLE"], SystemClock()
        )
        gateway = gateway or ApiGatewayGateway(
            boto3.client("apigatewaymanagementapi", endpoint_url=os.environ["WS_MANAGEMENT_URL"])
        )
    return {"sent": fan_out(registry, gateway, event.get("detail", {}))}
