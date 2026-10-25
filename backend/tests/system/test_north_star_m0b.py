"""Tier A north star — M0b (plan §3 M0b): two sessions converge; reconnect after 10 missed edits converges.

Everything in-process: the real API handler and SQL (StrictDataApiFake on PostgreSQL 18.6), the outbox payload
published to an InProcessBus in **chaos mode** (reordering + duplicates), the real fan-out into a fake WebSocket
gateway, and a client model that applies the same version rule as the SPA reconciler (web/src/sync/store.ts).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from tasklane.api.app import Deps, handle
from tasklane.collab.realtime import InMemoryRegistry, fan_out
from tasklane.platform.bus import Event, InProcessBus
from tasklane.platform.clock import FakeClock
from tasklane.platform.db import StrictDataApiFake

pytestmark = [pytest.mark.integration]
SUB = "00000000-0000-0000-0000-000000000042"


class BusPublisher:
    """PutEvents → InProcessBus (so chaos applies to delivery)."""

    def __init__(self, bus: InProcessBus) -> None:
        self.bus = bus

    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        for e in entries:
            d = json.loads(e["Detail"])
            self.bus.publish(Event(type=d["type"], event_id=d["event_id"], payload=d))
        return []


class Client:
    """Minimal port of the SPA reconciler: version rule + refetch on gap + gap sync via /changes."""

    def __init__(self, deps: Deps, name: str) -> None:
        self.deps, self.name = deps, name
        self.items: dict[str, dict[str, Any]] = {}
        self.cursor: str | None = None
        self.online = False
        self.conn = f"conn-{name}"

    def api(self, method: str, path: str, body: Any = None) -> Any:
        ev = {
            "version": "2.0",
            "routeKey": f"{method} {path}",
            "rawPath": path,
            "rawQueryString": "",
            "headers": {"content-type": "application/json"},
            "requestContext": {
                "http": {"method": method, "path": path, "sourceIp": "1.1.1.1"},
                "requestId": "r",
                "stage": "$default",
                "authorizer": {"jwt": {"claims": {"sub": SUB}}},
            },
            "body": json.dumps(body) if body is not None else None,
            "isBase64Encoded": False,
        }
        res = handle(ev, self.deps)
        assert res["statusCode"] == 200, res
        return json.loads(res["body"])

    def connect(self) -> None:
        t = self.api("POST", "/api/v1/realtime/ticket", {})["ticket"]
        user = self.deps.registry.redeem_ticket(t)
        assert user is not None
        self.deps.registry.connect(self.conn, user)
        self.deps.registry.subscribe(self.conn, 10)
        self.online = True

    def disconnect(self) -> None:
        self.deps.registry.disconnect(self.conn)
        self.online = False

    def start(self) -> None:
        self.connect()  # subscribe …
        self.cursor = self.api("POST", "/api/v1/boards/10/changes", {})["next_since_xmin"]  # … cursor …
        ids = self.api("POST", "/api/v1/boards/10/query", {})["ids"]  # … then snapshot
        self.refetch(ids)

    def refetch(self, ids: list[str]) -> None:
        for it in self.api("POST", "/api/v1/boards/10/items:fetch", {"ids": ids})["items"]:
            cur = self.items.get(it["id"])
            if cur is None or it["version"] >= cur["version"]:
                self.items[it["id"]] = it

    def on_message(self, m: dict[str, Any]) -> None:
        cur = self.items.get(m["item_id"])
        if cur is None or m["version"] <= cur["version"]:
            return
        if m["version"] > cur["version"] + 1:
            self.refetch([m["item_id"]])
            return
        vals = dict(cur["values"])
        for k, v in m["values"].items():
            if v is None:
                vals.pop(k, None)
            else:
                vals[k] = v
        self.items[m["item_id"]] = {**cur, "version": m["version"], "values": vals}

    def gap_sync(self) -> None:
        c = self.api("POST", "/api/v1/boards/10/changes", {"since_xmin": self.cursor})
        self.cursor = c["next_since_xmin"]
        self.refetch(sorted({x["item_id"] for x in c["changes"]}))


class Gateway:
    def __init__(self, clients: dict[str, Client]) -> None:
        self.clients = clients

    def send(self, conn: str, msg: dict[str, Any]) -> bool:
        c = self.clients.get(conn)
        if c is None or not c.online:
            return False
        c.on_message(msg)
        return True


@pytest.mark.parametrize("seed", [1, 7, 42, 2026])
def test_two_sessions_converge_and_reconnect_recovers_missed_edits(board_db: str, seed: int) -> None:
    bus = InProcessBus(chaos_seed=seed)
    clock = FakeClock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    deps = Deps(
        db=StrictDataApiFake(board_db),
        publisher=BusPublisher(bus),
        registry=InMemoryRegistry(clock),
        clock=clock,
        ws_url="/ws",
        bus_name="t",
    )
    a, b = Client(deps, "a"), Client(deps, "b")
    gw = Gateway({a.conn: a, b.conn: b})
    bus.subscribe("item.*", lambda e: fan_out(deps.registry, gw, e.payload))
    a.start()
    b.start()

    # 1. A edits a status; B converges via push (chaos: duplicates/reordering)
    a.api("PATCH", "/api/v1/items/1003/values", {"values": {"status": {"l": 1}}, "mutation_id": "m1"})
    bus.drain()
    assert b.items["1003"]["values"].get("status") == {"l": 1}

    # 2. B disconnects; A makes 10 edits across items; deliveries to B fail
    b.disconnect()
    for k in range(10):
        item = ["1001", "1002", "1003"][k % 3]
        a.api("PATCH", f"/api/v1/items/{item}/values", {"values": {"note": f"edit {k}", "amount": str(k)}})
        bus.drain()

    # 3. B reconnects (subscribe first, then gap sync) and converges with A and the server
    b.connect()
    b.gap_sync()
    a.gap_sync()
    server = {
        it["id"]: it
        for it in a.api("POST", "/api/v1/boards/10/items:fetch", {"ids": ["1001", "1002", "1003"]})["items"]
    }
    for item_id, it in server.items():
        assert b.items[item_id]["version"] == it["version"] and b.items[item_id]["values"] == it["values"]
        assert a.items[item_id]["version"] == it["version"] and a.items[item_id]["values"] == it["values"]
