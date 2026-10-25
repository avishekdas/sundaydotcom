"""Worker λ entry points wire ports from env (arch 05): acker, sweeper, scheduler-tick."""

from __future__ import annotations

import json
from typing import Any

from tasklane.platform.outbox import SweepReport
from tasklane.workers import outbox_acker, outbox_sweeper, scheduler_tick

ENV = {
    "CLUSTER_ARN": "arn:c",
    "DB_SECRET_ARN": "arn:s",
    "DB_NAME": "tasklane",
    "EVENT_BUS_NAME": "tasklane-dev",
}


def setenv(monkeypatch: Any) -> None:
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)


def test_acker_extracts_event_ids_from_sqs_records(monkeypatch: Any) -> None:
    setenv(monkeypatch)
    seen: dict[str, Any] = {}
    monkeypatch.setattr(outbox_acker, "ack", lambda db, ids, now: seen.setdefault("ids", ids) and len(ids))
    body = lambda eid: json.dumps({"detail-type": "x", "detail": {"event_id": eid}})  # noqa: E731
    event = {
        "Records": [
            {"messageId": "1", "body": body("e1")},
            {"messageId": "2", "body": body("e2")},
            {"messageId": "3", "body": "not json"},
        ]
    }
    out = outbox_acker.handler(event, None, rds_client=object())
    assert seen["ids"] == ["e1", "e2"]
    assert out == {"batchItemFailures": [{"itemIdentifier": "3"}]}


def test_sweeper_reports_metrics(monkeypatch: Any) -> None:
    setenv(monkeypatch)
    monkeypatch.setattr(
        outbox_sweeper, "sweep", lambda *a, **k: SweepReport(ran=True, republished=3, backlog=5)
    )
    out = outbox_sweeper.handler(
        {}, type("C", (), {"aws_request_id": "r1"})(), rds_client=object(), events_client=object()
    )
    assert out["republished"] == 3 and out["backlog"] == 5 and out["ran"] is True


def test_scheduler_tick_handler(monkeypatch: Any) -> None:
    setenv(monkeypatch)
    monkeypatch.setattr(scheduler_tick, "tick", lambda db: {"created": 0, "dropped": 1})
    assert scheduler_tick.handler({}, None, rds_client=object()) == {"created": 0, "dropped": 1}
