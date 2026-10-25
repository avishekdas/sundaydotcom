"""0003: table-scoped worker roles (M0A-4, SEC-11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg import errors
from psycopg.rows import dict_row

from tasklane.platform.clock import FakeClock
from tasklane.platform.db import PsycopgDb
from tasklane.platform.outbox import ack, sweep

pytestmark = pytest.mark.integration


def role_conn(uri: str, role: str) -> psycopg.Connection:
    c = psycopg.connect(uri, autocommit=True, row_factory=dict_row)
    c.execute(f"set role {role}")
    return c


def test_tl_worker_has_no_table_access_only_partition_functions(fresh_db: str) -> None:
    with role_conn(fresh_db, "tl_worker") as c:
        c.execute("select tl.ensure_partitions('tl.outbox', current_date, 1, 'day')")
        for sql in (
            "select 1 from tl.items limit 1",
            "delete from tl.users",
            "update tl.account set db_generation = 9",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(sql)


def test_outbox_worker_can_ack_and_sweep_but_nothing_else(fresh_db: str) -> None:
    now = datetime.now(UTC)
    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute(
            "insert into tl.outbox (event_id, type, payload, created_at) values "
            "('00000000-0000-0000-0000-000000000001', 't', '{}', %s)",
            (now - timedelta(minutes=2),),
        )
    with role_conn(fresh_db, "tl_worker_outbox") as c:
        db = PsycopgDb(fresh_db, _conn=c)

        class Pub:
            def put_events(self, entries: list[dict[str, object]]) -> list[int]:
                return []

        assert sweep(db, Pub(), FakeClock(now), holder="h", bus_name="b", source="tasklane").ran
        assert ack(db, ["00000000-0000-0000-0000-000000000001"], now=now) == 1
        for sql in (
            "delete from tl.outbox",
            "select 1 from tl.items limit 1",
            "update tl.outbox set payload = '{}'",
            "select tl.ensure_partitions('tl.outbox', current_date, 1, 'day')",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(sql)
