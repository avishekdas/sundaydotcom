"""scheduler-tick (PE-10): partitions ahead, retention drops, bounded by the DB (not the caller's clock)."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import dict_row

from tasklane.platform.db import StrictDataApiFake as PsycopgDb  # Data API typing (int8 params)
from tasklane.workers.scheduler_tick import tick

pytestmark = pytest.mark.integration


def parts(uri: str, parent: str) -> set[str]:
    with psycopg.connect(uri) as c:
        return {
            r[0]
            for r in c.execute(
                "select c.relname from pg_inherits i join pg_class c on c.oid = i.inhrelid where i.inhparent = %s::regclass",
                (parent,),
            ).fetchall()
        }


def test_tick_drops_expired_partitions_and_keeps_horizon(fresh_db: str) -> None:
    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute(
            "create table tl.outbox_p20200101 partition of tl.outbox for values from ('2020-01-01') to ('2020-01-02')"
        )
        c.execute(
            "create table tl.board_changes_p20200101 partition of tl.board_changes for values from ('2020-01-01') to ('2020-01-02')"
        )
        c.execute(
            "create table tl.activity_log_p202001 partition of tl.activity_log for values from ('2020-01-01') to ('2020-02-01')"
        )
    with psycopg.connect(fresh_db, autocommit=True, row_factory=dict_row) as c:
        c.execute("set role tl_worker")
        report = tick(PsycopgDb(fresh_db, _conn=c))
    assert "outbox_p20200101" not in parts(fresh_db, "tl.outbox")
    assert "board_changes_p20200101" not in parts(fresh_db, "tl.board_changes")
    assert "activity_log_p202001" not in parts(fresh_db, "tl.activity_log")
    assert len(parts(fresh_db, "tl.outbox")) >= 8 and report["dropped"] == 3


def test_retention_cannot_be_shortened_by_the_caller(fresh_db: str) -> None:
    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute("set role tl_worker")
        with pytest.raises(errors.RaiseException):
            c.execute("select tl.drop_partitions_older_than('tl.outbox', 1)")
    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute("set role tl_api_rw")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("select tl.drop_partitions_older_than('tl.outbox', 30)")
