"""Event schemas + previous-release replay (PE-6)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from tasklane.collab.realtime import InMemoryRegistry, fan_out
from tasklane.platform.clock import SystemClock
from tasklane.workers import outbox_acker

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "events"
SCHEMAS = {p.name.removesuffix(".json"): json.loads(p.read_text()) for p in CONTRACTS.glob("*.v*.json")}
FIXTURES = sorted((CONTRACTS / "fixtures").glob("*.json"))
EMITTED = {("item.values_changed", 1)}  # every (type, schema_version) the code emits today


def schema_for(event: dict) -> dict:  # type: ignore[type-arg]
    return SCHEMAS[f"{event['type']}.v{event['schema_version']}"]


def test_every_emitted_event_has_a_schema() -> None:
    for t, v in EMITTED:
        assert f"{t}.v{v}" in SCHEMAS


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixtures_match_their_schema(path: Path) -> None:
    ev = json.loads(path.read_text())
    jsonschema.validate(ev, schema_for(ev), format_checker=jsonschema.FormatChecker())


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_previous_release_events_replay_through_current_consumers(
    path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ev = json.loads(path.read_text())
    reg = InMemoryRegistry(SystemClock())
    reg.connect("c", 1)
    reg.subscribe("c", ev["board_id"])
    sent: list[dict] = []  # type: ignore[type-arg]

    class Gw:
        def send(self, _c: str, m: dict) -> bool:  # type: ignore[type-arg]
            sent.append(m)
            return True

    assert fan_out(reg, Gw(), ev) == 1 and sent[0]["item_id"] == str(ev["item_id"])
    acked: list[list[str]] = []
    monkeypatch.setattr(outbox_acker, "ack", lambda db, ids, now: acked.append(ids) or len(ids))
    monkeypatch.setattr(outbox_acker, "db_from_env", lambda _c=None: None)
    out = outbox_acker.handler({"Records": [{"messageId": "1", "body": json.dumps({"detail": ev})}]}, None)
    assert out == {"batchItemFailures": []} and acked == [[ev["event_id"]]]


@pytest.mark.integration
def test_set_values_emits_schema_valid_events(board_db: str) -> None:
    from tasklane.platform.db import StrictDataApiFake
    from tasklane.workmgmt.boards import Actor, set_values

    r = set_values(
        StrictDataApiFake(board_db), Actor(42, 0), 1003, {"status": {"l": 1}, "note": "x"}, mutation_id="m"
    )
    for e in r.events:
        detail = {
            "event_id": e.event_id,
            "type": e.type,
            "schema_version": e.schema_version,
            "board_id": e.board_id,
            "item_id": e.item_id,
            "payload": e.payload,
        }
        assert (e.type, e.schema_version) in EMITTED
        jsonschema.validate(detail, schema_for(detail), format_checker=jsonschema.FormatChecker())
