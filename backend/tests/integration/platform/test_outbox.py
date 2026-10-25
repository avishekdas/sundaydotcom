"""Durable publish (arch 05 §5.1; PE-5, OPS-5, OPS-16): after-commit PutEvents, acker, sweeper, circuit."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from tasklane.platform.clock import FakeClock
from tasklane.platform.db import StrictDataApiFake as PsycopgDb  # Data API typing (int8 params)
from tasklane.platform.outbox import OutboxEvent, ack, publish_after_commit, sweep, to_entry

pytestmark = pytest.mark.integration


class FakePublisher:
    """Records PutEvents batches; fail_ids makes those entries fail (FailedEntryCount) a given number of times."""

    def __init__(self, fail_ids: dict[str, int] | None = None) -> None:
        self.batches: list[list[dict[str, Any]]] = []
        self.fail_ids = dict(fail_ids or {})

    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        assert len(entries) <= 10
        self.batches.append(entries)
        failed = []
        for i, e in enumerate(entries):
            eid = json.loads(e["Detail"])["event_id"]
            if self.fail_ids.get(eid, 0) > 0:
                self.fail_ids[eid] -= 1
                failed.append(i)
        return failed

    @property
    def sent(self) -> list[str]:
        return [json.loads(e["Detail"])["event_id"] for b in self.batches for e in b]


def ev(i: int = 0) -> OutboxEvent:
    return OutboxEvent(
        event_id=str(uuid.UUID(int=i + 1)),
        type="item.values_changed",
        schema_version=1,
        board_id=10,
        item_id=1000 + i,
        payload={"k": i},
    )


def insert(
    uri: str,
    events: list[OutboxEvent],
    created_at: datetime,
    *,
    attempts: int = 0,
    last: datetime | None = None,
    published: datetime | None = None,
) -> None:
    with psycopg.connect(uri, autocommit=True) as c:
        for e in events:
            c.execute(
                """insert into tl.outbox (event_id, type, schema_version, board_id, item_id, payload, created_at,
                                          publish_attempts, last_published_at, published_at)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    e.event_id,
                    e.type,
                    e.schema_version,
                    e.board_id,
                    e.item_id,
                    json.dumps(e.payload),
                    created_at,
                    attempts,
                    last,
                    published,
                ),
            )


def unpublished(uri: str) -> set[str]:
    with psycopg.connect(uri) as c:
        return {
            str(r[0])
            for r in c.execute("select event_id from tl.outbox where published_at is null").fetchall()
        }


NOW = datetime.now(UTC).replace(microsecond=0)


def test_entry_envelope() -> None:
    entry = to_entry(ev(), bus_name="tasklane-dev", source="tasklane")
    assert entry["EventBusName"] == "tasklane-dev" and entry["Source"] == "tasklane"
    assert entry["DetailType"] == "item.values_changed"
    assert json.loads(entry["Detail"]) == {
        "event_id": ev().event_id,
        "type": "item.values_changed",
        "schema_version": 1,
        "board_id": 10,
        "item_id": 1000,
        "payload": {"k": 0},
    }


def test_publish_after_commit_batches_by_10_and_retries_partial_failures_once() -> None:
    events = [ev(i) for i in range(23)]
    pub = FakePublisher(fail_ids={events[3].event_id: 1, events[4].event_id: 5})
    failed = publish_after_commit(pub, events, bus_name="b", source="tasklane")
    assert [len(b) for b in pub.batches] == [10, 10, 3, 2]  # last batch: the inline retry of 2 failures
    assert failed == [events[4].event_id]  # still failing → left for the sweeper


def test_ack_marks_published_once(fresh_db: str) -> None:
    events = [ev(i) for i in range(12)]
    insert(fresh_db, events, NOW)
    db = PsycopgDb(fresh_db)
    assert ack(db, [e.event_id for e in events] + [events[0].event_id], now=NOW) == 12
    assert unpublished(fresh_db) == set()


def test_sweeper_republishes_after_grace_with_backoff_and_cap(fresh_db: str) -> None:
    clock = FakeClock(NOW)
    fresh = ev(0)  # 10 s old → within the 30 s grace, skipped
    due = ev(1)  # 2 min old, never retried → due
    backing_off = ev(2)  # attempts=2 → wait 2 min after last attempt; last was 1 min ago
    backed_off = ev(3)  # attempts=2, last 3 min ago → due
    insert(fresh_db, [fresh], NOW - timedelta(seconds=10))
    insert(fresh_db, [due], NOW - timedelta(minutes=2))
    insert(fresh_db, [backing_off], NOW - timedelta(minutes=30), attempts=2, last=NOW - timedelta(minutes=1))
    insert(fresh_db, [backed_off], NOW - timedelta(minutes=30), attempts=2, last=NOW - timedelta(minutes=3))
    insert(
        fresh_db, [ev(9)], NOW - timedelta(minutes=1), published=NOW
    )  # an ack within 5 min: circuit closed
    pub = FakePublisher()
    report = sweep(PsycopgDb(fresh_db), pub, clock, holder="t1", bus_name="b", source="tasklane", cap=500)
    assert sorted(pub.sent) == sorted([due.event_id, backed_off.event_id])
    assert report.republished == 2 and not report.circuit_open
    with psycopg.connect(fresh_db) as c:
        rows = dict(c.execute("select event_id::text, publish_attempts from tl.outbox").fetchall())
    assert rows[due.event_id] == 1 and rows[backed_off.event_id] == 3 and rows[fresh.event_id] == 0


def test_sweeper_cap_limits_rows_per_tick(fresh_db: str) -> None:
    insert(fresh_db, [ev(i) for i in range(30)], NOW - timedelta(minutes=2))
    insert(fresh_db, [ev(99)], NOW - timedelta(minutes=1), published=NOW)
    pub = FakePublisher()
    report = sweep(
        PsycopgDb(fresh_db), pub, FakeClock(NOW), holder="t1", bus_name="b", source="tasklane", cap=25
    )
    assert report.republished == 25 and report.backlog == 30


def test_lease_makes_the_sweeper_a_singleton(fresh_db: str) -> None:
    insert(fresh_db, [ev(1)], NOW - timedelta(minutes=2))
    db = PsycopgDb(fresh_db)
    clock = FakeClock(NOW)
    assert sweep(db, FakePublisher(), clock, holder="a", bus_name="b", source="tasklane").ran
    assert not sweep(db, FakePublisher(), clock, holder="b", bus_name="b", source="tasklane").ran
    clock.advance(minutes=3)  # lease (90 s) expired
    assert sweep(db, FakePublisher(), clock, holder="b", bus_name="b", source="tasklane").ran


def test_circuit_opens_when_nothing_is_acked_and_probes_one_row(fresh_db: str) -> None:
    # 40 events published 6-10 min ago by the API, none acked, no ack at all in the last 5 min → acker broken
    insert(fresh_db, [ev(i) for i in range(40)], NOW - timedelta(minutes=8))
    pub = FakePublisher()
    report = sweep(PsycopgDb(fresh_db), pub, FakeClock(NOW), holder="t1", bus_name="b", source="tasklane")
    assert report.circuit_open and report.republished == 1  # half-open probe only
    # the probe gets acked → circuit closes on the next tick
    ack(PsycopgDb(fresh_db), pub.sent, now=NOW + timedelta(seconds=30))
    clock = FakeClock(NOW + timedelta(minutes=2))
    report = sweep(PsycopgDb(fresh_db), FakePublisher(), clock, holder="t1", bus_name="b", source="tasklane")
    assert not report.circuit_open and report.republished == 39
