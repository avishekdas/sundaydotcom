"""WebSocket route handler (ADR-005)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from tasklane.collab.realtime import InMemoryRegistry
from tasklane.platform.clock import FakeClock
from tasklane.workers import fanout
from tasklane.workers.ws_handlers import handle


def ev(route: str, conn: str = "c1", **kw: Any) -> dict[str, Any]:
    return {"requestContext": {"routeKey": route, "connectionId": conn}, **kw}


def test_connect_needs_a_valid_ticket_then_subscribe() -> None:
    reg = InMemoryRegistry(FakeClock(datetime(2026, 10, 25, tzinfo=UTC)))
    assert handle(ev("$connect"), reg)["statusCode"] == 401
    t = reg.issue_ticket(42)
    assert handle(ev("$connect", queryStringParameters={"ticket": t}), reg)["statusCode"] == 200
    assert (
        handle(ev("$connect", "c2", queryStringParameters={"ticket": t}), reg)["statusCode"] == 401
    )  # reused
    r = handle(ev("$default", body=json.dumps({"action": "subscribe", "board_id": "10"})), reg)
    assert r["statusCode"] == 200 and reg.subscribers(10) == ["c1"]
    assert (
        handle(ev("$default", "c9", body=json.dumps({"action": "subscribe", "board_id": "10"})), reg)[
            "statusCode"
        ]
        == 401
    )
    handle(ev("$disconnect"), reg)
    assert reg.subscribers(10) == []


def test_fanout_handler_uses_event_detail() -> None:
    reg = InMemoryRegistry(FakeClock(datetime(2026, 10, 25, tzinfo=UTC)))
    reg.connect("c1", 42)
    reg.subscribe("c1", 10)
    sent: list[Any] = []

    class Gw:
        def send(self, c: str, m: dict[str, Any]) -> bool:
            sent.append((c, m))
            return True

    detail = {
        "event_id": "e",
        "type": "item.values_changed",
        "board_id": 10,
        "item_id": 1,
        "payload": {"changes": []},
    }
    assert fanout.handler({"detail": detail}, None, registry=reg, gateway=Gw()) == {"sent": 1}
