"""Mutation builder against PostgreSQL 18.6 through the StrictDataApiFake (arch 03 §3.5; PE-9)."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from tasklane.platform.db import StrictDataApiFake
from tasklane.platform.migrations import apply_migrations
from tasklane.platform.mutation import classify_failure, run, set_cell_value

pytestmark = pytest.mark.integration
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
ITEM, CHILD, BOARD = 1001, 1002, 10


@pytest.fixture
def uri(pg_uri: str) -> Iterator[str]:
    name = "mut_" + uuid.uuid4().hex[:8]
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"create database {name}")
    u = make_conninfo(pg_uri, dbname=name)
    apply_migrations(u, MIGRATIONS)
    with psycopg.connect(u, autocommit=True) as c:
        c.execute("insert into tl.workspaces (id, name, kind, position) values (1, 'W', 'open', 'a')")
        c.execute(
            f"insert into tl.boards (id, workspace_id, name, kind, position) values ({BOARD}, 1, 'B', 'main', 'a')"
        )
        c.execute(
            f"insert into tl.groups (id, board_id, title, color, position) values (100, {BOARD}, 'G', 'blue', 'a')"
        )
        c.execute(f"""insert into tl.items (id, board_id, group_id, name, position, created_by_type, values)
                      values ({ITEM}, {BOARD}, 100, 'Deal', 'a', 'user', '{{"owner": {{"p": [{{"t": "u", "id": 42}}]}}}}')""")
        c.execute(f"""insert into tl.items (id, board_id, group_id, parent_item_id, name, position, created_by_type)
                      values ({CHILD}, {BOARD}, 100, {ITEM}, 'Sub', 'b', 'user')""")
    yield u


def write(
    db: StrictDataApiFake,
    item: int = ITEM,
    *,
    value: object = {"i": 1},
    epoch: int = 0,
    assign: str | None = None,
    uid: int = 42,
) -> object:
    m = set_cell_value(
        item_id=item,
        column_id="status",
        value=value,
        assign_column_id=assign,
        actor_type="user",
        actor_id=uid,
        cached_epoch=epoch,
        mutation_id="m-" + uuid.uuid4().hex,
        event_id=str(uuid.uuid4()),
    )
    return run(db, m)


def counts(uri: str) -> dict[str, int]:
    with psycopg.connect(uri) as c:
        return {
            t: c.execute(f"select count(*) from tl.{t}").fetchone()[0]  # type: ignore[index]
            for t in ("activity_log", "board_changes", "outbox", "recompute_pending")
        }


def test_cell_write_updates_value_and_writes_all_side_rows_in_one_statement(uri: str) -> None:
    db = StrictDataApiFake(uri)
    res = write(db)
    assert res.ok and res.version == 2 and res.seq is not None  # type: ignore[attr-defined]
    with psycopg.connect(uri) as c:
        v, ver = c.execute(f"select values->'status', version from tl.items where id = {ITEM}").fetchone()  # type: ignore[misc]
        assert (v, ver) == ({"i": 1}, 2)
        act = c.execute("select kind, column_id, before, after from tl.activity_log").fetchall()
        assert act == [("value", "status", None, {"i": 1})]
        ch = c.execute("select board_id, item_id, kind, columns from tl.board_changes").fetchall()
        assert ch == [(BOARD, ITEM, "value", ["status"])]
        (payload,) = c.execute("select payload from tl.outbox").fetchone()  # type: ignore[misc]
        assert payload["changes"] == [{"col": "status", "old": None, "new": {"i": 1}}]
        assert payload["version"] == 2 and payload["seq"] == res.seq  # type: ignore[attr-defined]
    assert counts(uri)["recompute_pending"] == 1


def test_stale_epoch_writes_nothing_and_is_classified(uri: str) -> None:
    db = StrictDataApiFake(uri)
    res = write(db, epoch=99)
    assert not res.ok  # type: ignore[attr-defined]
    assert classify_failure(db, item_id=ITEM, cached_epoch=99) == "stale_epoch"
    assert counts(uri) == {"activity_log": 0, "board_changes": 0, "outbox": 0, "recompute_pending": 0}


def test_missing_or_deleted_item_is_not_found(uri: str) -> None:
    db = StrictDataApiFake(uri)
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute(f"update tl.items set state = 'deleted' where id = {CHILD}")
    for item in (CHILD, 999_999):
        assert not write(db, item).ok  # type: ignore[attr-defined]
        assert classify_failure(db, item_id=item, cached_epoch=0) == "not_found"


def test_edit_assigned_guard(uri: str) -> None:
    db = StrictDataApiFake(uri)
    assert write(db, assign="owner", uid=42).ok  # type: ignore[attr-defined]          # assigned on the item
    assert not write(db, assign="owner", uid=7).ok  # type: ignore[attr-defined]       # not assigned
    assert classify_failure(db, item_id=ITEM, cached_epoch=0) == "forbidden"
    assert write(db, CHILD, assign="owner", uid=42).ok  # type: ignore[attr-defined]   # assigned on the parent


def test_concurrent_writes_serialize_without_lost_updates(uri: str) -> None:
    n = 16
    errors: list[BaseException] = []

    def worker(k: int) -> None:
        try:
            db = StrictDataApiFake(uri)
            assert write(db, value={"i": k}).ok  # type: ignore[attr-defined]
            db.close()
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    with psycopg.connect(uri) as c:
        (ver,) = c.execute(f"select version from tl.items where id = {ITEM}").fetchone()  # type: ignore[misc]
        versions = sorted(
            r[0] for r in c.execute("select (payload->>'version')::int from tl.outbox").fetchall()
        )
        chain = c.execute("select before, after from tl.activity_log order by id").fetchall()
    assert ver == n + 1 and versions == list(range(2, n + 2))
    # every write saw the previous write's value as its pre-image: the before/after chain is unbroken
    afters = {str(a) for _, a in chain}
    assert sum(1 for b, _ in chain if b is None) == 1 and all(
        str(b) in afters for b, _ in chain if b is not None
    )
