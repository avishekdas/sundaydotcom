"""Skeleton board service (M0b story 6): schema, ordered query, hydration, value writes, change cursor."""

from __future__ import annotations

import psycopg
import pytest

from tasklane.platform.db import StrictDataApiFake
from tasklane.workmgmt.boards import (
    Actor,
    ValidationFailed,
    changes,
    fetch_items,
    get_schema,
    query_board,
    set_values,
)

pytestmark = pytest.mark.integration
ADA = Actor(user_id=42, cached_epoch=0)


def test_schema_lists_columns_and_groups_in_order(board_db: str) -> None:
    s = get_schema(StrictDataApiFake(board_db), 10)
    assert s["board"]["id"] == "10" and s["board"]["name"] == "Board 10"
    assert [g["id"] for g in s["groups"]] == ["100", "101"]
    assert [(c["id"], c["type"]) for c in s["columns"]] == [
        ("status", "status"),
        ("note", "text"),
        ("amount", "numbers"),
    ]
    assert s["columns"][0]["settings"]["labels"][1]["text"] == "Done"


def test_unknown_board_is_none(board_db: str) -> None:
    assert get_schema(StrictDataApiFake(board_db), 999) is None


def test_query_returns_ids_in_group_then_item_order_with_counts(board_db: str) -> None:
    q = query_board(StrictDataApiFake(board_db), 10)
    assert q["ids"] == ["1003", "1002", "1001"]
    assert q["groups"] == [{"id": "100", "count": 2}, {"id": "101", "count": 1}]


def test_fetch_hydrates_only_items_of_the_board(board_db: str) -> None:
    rows = fetch_items(StrictDataApiFake(board_db), 10, ["1003", "2001", "1001"])
    assert [r["id"] for r in rows] == ["1003", "1001"]
    assert rows[0] == {
        "id": "1003",
        "name": "First",
        "group_id": "100",
        "version": 1,
        "values": {},
        "computed": {},
    }
    with pytest.raises(ValidationFailed):
        fetch_items(StrictDataApiFake(board_db), 10, [str(i) for i in range(201)])


def test_set_values_validates_writes_several_columns_and_removes_empties(board_db: str) -> None:
    db = StrictDataApiFake(board_db)
    r = set_values(db, ADA, 1003, {"status": {"l": 1}, "note": " hi ", "amount": "1,200"}, mutation_id="m1")
    assert r.version == 2 and set(r.values) == {"status", "note", "amount"}
    assert r.values == {"status": {"l": 1}, "note": "hi", "amount": "1200"}
    assert len(r.events) == 1 and r.events[0].type == "item.values_changed"
    assert sorted(c["col"] for c in r.events[0].payload["changes"]) == ["amount", "note", "status"]
    r2 = set_values(db, ADA, 1003, {"note": ""}, mutation_id="m2")
    assert r2.version == 3 and r2.values == {"note": None}
    (vals,) = (fetch_items(db, 10, ["1003"])[0]["values"],)
    assert vals == {"status": {"l": 1}, "amount": "1200"}
    with psycopg.connect(board_db) as c:
        assert c.execute("select count(*) from tl.activity_log").fetchone() == (4,)


def test_set_values_rejects_bad_values_and_unknown_columns(board_db: str) -> None:
    db = StrictDataApiFake(board_db)
    with pytest.raises(ValidationFailed) as e:
        set_values(db, ADA, 1003, {"status": {"l": 9}, "nope": "x"}, mutation_id="m")
    assert set(e.value.fields) == {"values.status", "values.nope"}


def test_set_values_on_missing_item_or_wrong_epoch(board_db: str) -> None:
    db = StrictDataApiFake(board_db)
    assert set_values(db, ADA, 999, {"note": "x"}, mutation_id="m").failure == "not_found"
    assert (
        set_values(db, Actor(42, cached_epoch=5), 1003, {"note": "x"}, mutation_id="m").failure
        == "stale_epoch"
    )


def test_change_cursor_returns_writes_after_the_cursor_exactly_once(board_db: str) -> None:
    db = StrictDataApiFake(board_db)
    start = changes(db, 10, since_xmin=None)
    assert start["changes"] == [] and start["db_generation"] == 1
    set_values(db, ADA, 1003, {"note": "a"}, mutation_id="m1")
    set_values(db, ADA, 1002, {"note": "b"}, mutation_id="m2")
    set_values(db, ADA, 2001 if False else 1001, {"note": "c"}, mutation_id="m3")
    first = changes(db, 10, since_xmin=start["next_since_xmin"])
    assert [c["item_id"] for c in first["changes"]] == ["1003", "1002", "1001"]
    again = changes(db, 10, since_xmin=first["next_since_xmin"])
    assert again["changes"] == []
