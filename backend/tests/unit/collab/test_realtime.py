"""Realtime registry (arch 05 §5.2; AR-10, D-018): single-use tickets, connections, board subscriptions, fan-out."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tasklane.collab.realtime import InMemoryRegistry, Registry, fan_out
from tasklane.platform.clock import FakeClock

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def test_ticket_is_single_use_and_expires_after_30s() -> None:
    clock = FakeClock(T0)
    reg: Registry = InMemoryRegistry(clock)
    t = reg.issue_ticket(user_id=42)
    assert len(t) >= 32
    assert reg.redeem_ticket(t) == 42
    assert reg.redeem_ticket(t) is None              # single use
    t2 = reg.issue_ticket(user_id=42)
    clock.advance(seconds=31)
    assert reg.redeem_ticket(t2) is None             # expired


def test_subscriptions_and_disconnect_cleanup() -> None:
    reg = InMemoryRegistry(FakeClock(T0))
    reg.connect("c1", 42)
    reg.connect("c2", 7)
    reg.subscribe("c1", 10)
    reg.subscribe("c2", 10)
    reg.subscribe("c2", 20)
    assert sorted(reg.subscribers(10)) == ["c1", "c2"]
    reg.disconnect("c2")
    assert reg.subscribers(10) == ["c1"] and reg.subscribers(20) == []
    assert reg.user_of("c1") == 42 and reg.user_of("c2") is None


class FakeGateway:
    def __init__(self, gone: set[str] | None = None) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.gone = gone or set()

    def send(self, connection_id: str, message: dict[str, Any]) -> bool:
        if connection_id in self.gone:
            return False
        self.sent.append((connection_id, message))
        return True


def test_fan_out_sends_board_events_to_subscribers_and_drops_gone_connections() -> None:
    reg = InMemoryRegistry(FakeClock(T0))
    for c in ("c1", "c2", "c3"):
        reg.connect(c, 42)
        reg.subscribe(c, 10)
    reg.connect("c4", 42)
    reg.subscribe("c4", 20)
    gw = FakeGateway(gone={"c2"})
    detail = {"event_id": "e1", "type": "item.values_changed", "board_id": 10, "item_id": 1003,
              "payload": {"changes": [{"col": "status", "old": None, "new": {"l": 1}}], "version": 2, "seq": 5,
                          "mutation_id": "m1"}}
    n = fan_out(reg, gw, detail)
    assert n == 2 and sorted(c for c, _ in gw.sent) == ["c1", "c3"]
    msg = gw.sent[0][1]
    assert msg == {"type": "item.values_changed", "event_id": "e1", "board_id": "10", "item_id": "1003",
                   "version": 2, "seq": 5, "mutation_id": "m1", "values": {"status": {"l": 1}}}
    assert reg.subscribers(10) == ["c1", "c3"] or sorted(reg.subscribers(10)) == ["c1", "c3"]
