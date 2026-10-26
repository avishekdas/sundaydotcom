"""Runner: no-transaction mode for CREATE INDEX CONCURRENTLY (PE-4)."""

from __future__ import annotations

import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from tasklane.platform.db import StrictDataApiFake
from tasklane.platform.migrations import apply_migrations

pytestmark = pytest.mark.integration
REAL = Path(__file__).resolve().parents[3] / "migrations"


def test_no_transaction_migration_runs_concurrent_index(pg_uri: str, tmp_path: Path) -> None:
    for p in REAL.glob("*.sql"):
        (tmp_path / p.name).write_text(p.read_text())
    n = len(list(REAL.glob("*.sql")))
    (tmp_path / f"{n:04d}_items_name_idx.sql").write_text(
        "-- run-mode: no-transaction\ncreate index concurrently if not exists items_name_idx on tl.items (name);\n"
    )
    name = "nt_" + uuid.uuid4().hex[:8]
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"create database {name}")
    uri = make_conninfo(pg_uri, dbname=name)
    applied = apply_migrations(StrictDataApiFake(uri), tmp_path)
    assert applied[-1] == f"{n:04d}"
    with psycopg.connect(uri) as c:
        owner = c.execute("select tableowner from pg_tables where tablename = 'items'").fetchone()
        idx = c.execute("select indexname from pg_indexes where indexname = 'items_name_idx'").fetchone()
    assert idx is not None and owner == ("tl_migrator",)


def test_no_transaction_runs_take_a_lease(pg_uri: str, tmp_path: Path) -> None:
    """M0B-10: a second runner (pipeline + a manual invoke) must not run no-transaction statements twice."""
    for p in REAL.glob("*.sql"):
        (tmp_path / p.name).write_text(p.read_text())
    n = len(list(REAL.glob("*.sql")))
    (tmp_path / f"{n:04d}_items_name_idx.sql").write_text(
        "-- run-mode: no-transaction\ncreate index concurrently if not exists items_name_idx on tl.items (name);\n"
    )
    name = "nl_" + uuid.uuid4().hex[:8]
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"create database {name}")
    uri = make_conninfo(pg_uri, dbname=name)
    apply_migrations(StrictDataApiFake(uri), REAL)  # schema (and tl.leases) in place
    with psycopg.connect(uri, autocommit=True) as c:  # another runner holds the lease
        c.execute(
            "insert into tl.leases (name, holder, until) values ('migrations', 'other', now() + interval '5 min') "
            "on conflict (name) do update set holder = excluded.holder, until = excluded.until"
        )
    with pytest.raises(RuntimeError, match="lease"):
        apply_migrations(StrictDataApiFake(uri), tmp_path)
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute("update tl.leases set until = now() - interval '1 s' where name = 'migrations'")
    assert apply_migrations(StrictDataApiFake(uri), tmp_path) == [f"{n:04d}"]
    with psycopg.connect(uri) as c:
        row = c.execute("select until < now() from tl.leases where name = 'migrations'").fetchone()
    assert row == (True,)  # released
