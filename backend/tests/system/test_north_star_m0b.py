"""Tier A north star — M0b (plan §3 M0b): two sessions converge; reconnect after 10 missed edits converges.

Everything in-process: the real API handler and SQL (StrictDataApiFake on PostgreSQL 18.6), the outbox payload
published to an InProcessBus in **chaos mode** (reordering + duplicates), the real fan-out into a fake WebSocket
gateway, and a client model that applies the same version rule as the SPA reconciler (web/src/sync/store.ts).
"""

from __future__ import annotations

import json
import os
import random
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
        ids: set[str] = set()
        while True:
            c = self.api("POST", "/api/v1/boards/10/changes", {"since_xmin": self.cursor})
            self.cursor = c["next_since_xmin"]
            ids |= {x["item_id"] for x in c["changes"]}
            if not c.get("more"):
                break
        self.refetch(sorted(ids))


class Gateway:
    def __init__(self, clients: dict[str, Client]) -> None:
        self.clients = clients

    def send(self, conn: str, msg: dict[str, Any]) -> bool:
        c = self.clients.get(conn)
        if c is None or not c.online:
            return False
        c.on_message(msg)
        return True


def server_state(c: Client) -> dict[str, dict[str, Any]]:
    rows = c.api("POST", "/api/v1/boards/10/items:fetch", {"ids": ["1001", "1002", "1003"]})["items"]
    return {it["id"]: {"version": it["version"], "values": it["values"]} for it in rows}


def state(c: Client) -> dict[str, dict[str, Any]]:
    return {
        i: {"version": c.items[i]["version"], "values": c.items[i]["values"]}
        for i in ("1001", "1002", "1003")
    }


FIXED_SEEDS = [1, 7, 42, 2026]


def _seeds() -> list[int]:
    """PRs run the fixed seeds; the nightly job adds TL_CHAOS_SEEDS rotating ones (TP-12), chosen from the date so a
    failing night is reproducible — the failing seed is in the test id; promote it into FIXED_SEEDS."""
    extra = int(os.environ.get("TL_CHAOS_SEEDS", "0"))
    rng = random.Random(int(datetime.now(UTC).strftime("%Y%m%d")))  # noqa: S311 — reproducible test seeds
    return FIXED_SEEDS + [rng.randrange(1, 2**31) for _ in range(extra)]


@pytest.mark.north_star("skeleton.converge")
@pytest.mark.parametrize("seed", _seeds())
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
    delivered: list[tuple[str, int]] = []

    def on_event(e: Event) -> None:
        delivered.append((e.payload["item_id"], e.payload["payload"]["version"]))
        fan_out(deps.registry, gw, e.payload)

    bus.subscribe("item.*", on_event)
    a.start()
    b.start()

    # 1. A makes several edits; the bus holds them all, then delivers with chaos (reordering + duplicates).
    #    Both sessions must converge through pushes alone — no gap sync.
    published: list[tuple[str, int]] = []
    for k in range(9):
        item = ["1001", "1002", "1003"][k % 3]
        r = a.api(
            "PATCH",
            f"/api/v1/items/{item}/values",
            {"values": {"status": {"l": k % 3}, "amount": str(k)}, "mutation_id": f"m{k}"},
        )
        published.append((item, r["version"]))
    bus.drain()
    assert delivered != published, "chaos must reorder or duplicate deliveries"
    truth = server_state(a)
    assert state(a) == truth and state(b) == truth

    # 2. B disconnects; A makes 10 more edits (deliveries to B fail); A stays converged by pushes only
    b.disconnect()
    for k in range(10):
        item = ["1001", "1002", "1003"][k % 3]
        a.api(
            "PATCH", f"/api/v1/items/{item}/values", {"values": {"note": f"edit {k}", "amount": str(100 + k)}}
        )
    bus.drain()
    truth = server_state(a)
    assert state(a) == truth
    assert state(b) != truth

    # 3. B reconnects (subscribe first, then gap sync) and converges — value and version for every item
    b.connect()
    b.gap_sync()
    assert state(b) == truth
