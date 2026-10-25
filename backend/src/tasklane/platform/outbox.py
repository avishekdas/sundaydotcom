"""Durable publish (arch 05 §5.1; PE-5, OPS-5, OPS-16).

1. The mutation statement inserts the outbox row (``Mutation`` fragment ``o``).
2. After it returns, the caller publishes with ``publish_after_commit`` (PutEvents, partial failures retried
   inline once) and responds; it does not mark the row.
3. ``ack`` (outbox-acker λ, fed by an EventBridge rule → SQS) sets ``published_at``.
4. ``sweep`` (outbox-sweeper, every minute, singleton by lease) republishes unacked rows older than 30 s with
   per-row exponential backoff (30 s · 2^attempts, max 1 h), at most ``cap`` rows per tick. If nothing has
   been acked for 5 minutes while the API kept publishing, the acker is presumed broken: the circuit opens
   and each tick republishes a single probe row until an ack arrives (protects consumers from floods).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from tasklane.platform.clock import Clock
from tasklane.platform.db import Db, Json

PUT_EVENTS_BATCH = 10
ENTRY_LIMIT_BYTES = 256 * 1024
GRACE = timedelta(seconds=30)
LEASE = timedelta(seconds=90)
CIRCUIT_WINDOW = timedelta(minutes=5)
CIRCUIT_MIN_UNACKED = 20
PAGE = 50  # rows per read: keeps each Data API response well under 1 MiB (payloads ≤ 28 KB, PE-11)


class Publisher(Protocol):
    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        """Send ≤ 10 entries; return the indexes of failed entries."""
        ...


class EventBridgePublisher:
    def __init__(self, client: Any) -> None:
        self._client = client

    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        res = self._client.put_events(Entries=entries)
        return [i for i, r in enumerate(res.get("Entries", [])) if r.get("ErrorCode")]


@dataclass(frozen=True)
class OutboxEvent:
    event_id: str
    type: str
    schema_version: int
    board_id: int | None
    item_id: int | None
    payload: dict[str, Any] = field(default_factory=dict)


def to_entry(e: OutboxEvent, *, bus_name: str, source: str) -> dict[str, Any]:
    detail = json.dumps(
        {
            "event_id": e.event_id,
            "type": e.type,
            "schema_version": e.schema_version,
            "board_id": e.board_id,
            "item_id": e.item_id,
            "payload": e.payload,
        },
        separators=(",", ":"),
        default=str,
    )
    if len(detail.encode()) > ENTRY_LIMIT_BYTES:
        raise ValueError(f"event {e.event_id} exceeds the EventBridge 256 KB entry limit")
    return {"EventBusName": bus_name, "Source": source, "DetailType": e.type, "Detail": detail}


def _batches(xs: Sequence[OutboxEvent]) -> Iterable[Sequence[OutboxEvent]]:
    for i in range(0, len(xs), PUT_EVENTS_BATCH):
        yield xs[i : i + PUT_EVENTS_BATCH]


def _put(
    publisher: Publisher, events: Sequence[OutboxEvent], bus_name: str, source: str
) -> list[OutboxEvent]:
    failed: list[OutboxEvent] = []
    for batch in _batches(events):
        idx = publisher.put_events([to_entry(e, bus_name=bus_name, source=source) for e in batch])
        failed.extend(batch[i] for i in idx)
    return failed


def publish_after_commit(
    publisher: Publisher, events: Sequence[OutboxEvent], *, bus_name: str, source: str
) -> list[str]:
    """Publish; retry partial failures inline once. Returns ids still failing (the sweeper picks them up)."""
    failed = _put(publisher, events, bus_name, source)
    if failed:
        failed = _put(publisher, failed, bus_name, source)
    return [e.event_id for e in failed]


def ack(db: Db, event_ids: Sequence[str], *, now: datetime) -> int:
    """Mark events published. Bounded to the 8-day retention window for partition pruning."""
    ids = sorted(set(event_ids))
    if not ids:
        return 0
    return db.execute(
        """update tl.outbox set published_at = :now
           where event_id in (select (jsonb_array_elements_text(:ids::jsonb))::uuid)
             and created_at >= :since and published_at is null""",
        {"now": now, "ids": Json(ids), "since": now - timedelta(days=8)},
    )


@dataclass(frozen=True)
class SweepReport:
    ran: bool
    republished: int = 0
    failed: int = 0
    backlog: int = 0
    max_attempts: int = 0
    circuit_open: bool = False


def _take_lease(db: Db, name: str, holder: str, now: datetime) -> bool:
    rows = db.query(
        """insert into tl.leases (name, holder, until) values (:name, :holder, :until)
           on conflict (name) do update set holder = excluded.holder, until = excluded.until
             where tl.leases.until < :now or tl.leases.holder = excluded.holder
           returning holder""",
        {"name": name, "holder": holder, "until": now + LEASE, "now": now},
    )
    return bool(rows)


def _circuit_open(db: Db, now: datetime) -> bool:
    rows = db.query(
        """select (select count(*) from tl.outbox where published_at > :recent) as acked,
                  (select count(*) from tl.outbox where published_at is null
                     and created_at between :old_from and :recent) as unacked""",
        {"recent": now - CIRCUIT_WINDOW, "old_from": now - 3 * CIRCUIT_WINDOW},
    )
    r = rows[0]
    return int(r["acked"]) == 0 and int(r["unacked"]) >= CIRCUIT_MIN_UNACKED


def sweep(
    db: Db, publisher: Publisher, clock: Clock, *, holder: str, bus_name: str, source: str, cap: int = 500
) -> SweepReport:
    now = clock.now()
    if not _take_lease(db, "outbox-sweeper", holder, now):
        return SweepReport(ran=False)
    stats = db.query(
        """select count(*) as backlog, coalesce(max(publish_attempts), 0) as max_attempts from tl.outbox
           where published_at is null and created_at < :due and created_at >= :since""",
        {"due": now - GRACE, "since": now - timedelta(days=8)},
    )[0]
    circuit = _circuit_open(db, now)
    limit = 1 if circuit else cap
    republished = failed = 0
    while republished + failed < limit:
        rows = db.query(
            """select event_id::text as event_id, type, schema_version, board_id, item_id, payload::text as payload
               from tl.outbox
               where published_at is null and created_at < :due and created_at >= :since
                 and (last_published_at is null
                      or last_published_at <= :now - least(interval '30 seconds' * power(2, publish_attempts),
                                                           interval '1 hour'))
               order by created_at, id limit :n""",
            {
                "due": now - GRACE,
                "since": now - timedelta(days=8),
                "now": now,
                "n": min(PAGE, limit - republished - failed),
            },
        )
        if not rows:
            break
        events = [
            OutboxEvent(
                r["event_id"],
                r["type"],
                int(r["schema_version"]),
                r["board_id"],
                r["item_id"],
                json.loads(r["payload"]),
            )
            for r in rows
        ]
        still = set(_put(publisher, events, bus_name, source))
        db.execute(
            """update tl.outbox set publish_attempts = publish_attempts + 1, last_published_at = :now
               where event_id in (select (jsonb_array_elements_text(:ids::jsonb))::uuid) and created_at >= :since""",
            {"now": now, "ids": Json([e.event_id for e in events]), "since": now - timedelta(days=8)},
        )
        failed += len(still)
        republished += len(events) - len(still)
    return SweepReport(
        ran=True,
        republished=republished,
        failed=failed,
        backlog=int(stats["backlog"]),
        max_attempts=int(stats["max_attempts"]),
        circuit_open=circuit,
    )
