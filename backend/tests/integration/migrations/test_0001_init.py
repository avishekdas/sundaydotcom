"""0000_bootstrap + 0001_init: schema, states, db_generation, partitions, Postgres roles per function class (PE-8, SEC-11)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import errors
from psycopg.conninfo import make_conninfo

from tasklane.platform.migrations import apply_migrations, discover

pytestmark = pytest.mark.integration
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


@pytest.fixture(scope="module")
def db_uri(pg_uri: str) -> Iterator[str]:
    name = "mig_" + uuid.uuid4().hex[:8]
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"create database {name}")
    uri = make_conninfo(pg_uri, dbname=name)
    apply_migrations(uri, MIGRATIONS)
    yield uri


def as_role(uri: str, role: str) -> psycopg.Connection:
    c = psycopg.connect(uri, autocommit=True)
    c.execute(f"set role {role}")
    return c


def seed(c: psycopg.Connection) -> None:
    c.execute(
        "insert into tl.workspaces (id, name, kind, position) values (1, 'W', 'open', 'a') on conflict do nothing"
    )
    c.execute(
        "insert into tl.boards (id, workspace_id, name, kind, position) values (1, 1, 'B', 'main', 'a') on conflict do nothing"
    )
    c.execute(
        "insert into tl.groups (id, board_id, title, color, position) values (1, 1, 'G', 'blue', 'a') on conflict do nothing"
    )


def test_discover_orders_and_rejects_gaps(tmp_path: Path) -> None:
    (tmp_path / "0001_b.sql").write_text("select 1;")
    (tmp_path / "0000_a.sql").write_text("select 1;")
    assert [m.version for m in discover(tmp_path)] == ["0000", "0001"]
    (tmp_path / "0003_c.sql").write_text("select 1;")
    with pytest.raises(ValueError, match="gap"):
        discover(tmp_path)


def test_apply_is_idempotent_and_recorded(db_uri: str) -> None:
    assert apply_migrations(db_uri, MIGRATIONS) == []
    with psycopg.connect(db_uri) as c:
        rows = c.execute("select version from tl.schema_migrations order by version").fetchall()
    assert [r[0] for r in rows][:2] == ["0000", "0001"]


def test_changed_applied_migration_is_rejected(db_uri: str, tmp_path: Path) -> None:
    for m in discover(MIGRATIONS):
        (tmp_path / m.path.name).write_text(m.sql + "\n-- edited\n")
    with pytest.raises(RuntimeError, match="checksum"):
        apply_migrations(db_uri, tmp_path)


def test_account_singleton_with_db_generation(db_uri: str) -> None:
    with psycopg.connect(db_uri, autocommit=True) as c:
        c.execute("insert into tl.account (name, date_format, week_start) values ('Acme', 'YYYY-MM-DD', 1)")
        assert c.execute("select db_generation, perm_epoch from tl.account").fetchone() == (1, 0)
        with pytest.raises(errors.CheckViolation):
            c.execute("insert into tl.account (id, name, date_format, week_start) values (2, 'X', 'd', 1)")


@pytest.mark.parametrize("table", ["workspaces", "boards", "groups", "columns", "items"])
def test_state_is_constrained(db_uri: str, table: str) -> None:
    with psycopg.connect(db_uri) as c:
        (definition,) = c.execute(
            "select pg_get_constraintdef(oid) from pg_constraint where conrelid = %s::regclass and conname = %s",
            (f"tl.{table}", f"{table}_state_check"),
        ).fetchone() or (None,)
    assert definition is not None and all(s in definition for s in ("active", "archived", "deleted"))


def test_board_changes_and_outbox_have_todays_partition(db_uri: str) -> None:
    with psycopg.connect(db_uri, autocommit=True) as c:
        c.execute("insert into tl.board_changes (board_id, kind) values (1, 'value')")
        c.execute("insert into tl.outbox (event_id, type, payload) values (gen_random_uuid(), 't', '{}')")
        xid = c.execute("select xid from tl.board_changes limit 1").fetchone()
        assert xid is not None and int(str(xid[0])) > 0
        before = c.execute(
            "select count(*) from pg_inherits where inhparent = 'tl.outbox'::regclass"
        ).fetchone()
        c.execute("select tl.ensure_daily_partitions('tl.outbox', current_date, 3)")
        after = c.execute(
            "select count(*) from pg_inherits where inhparent = 'tl.outbox'::regclass"
        ).fetchone()
    assert before == after  # idempotent; migration pre-creates today + 2 days


def test_reader_cannot_write(db_uri: str) -> None:
    with as_role(db_uri, "tl_reader") as c:
        c.execute("select count(*) from tl.items")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("insert into tl.workspaces (id, name, kind, position) values (9, 'x', 'open', 'a')")


def test_api_rw_has_dml_but_no_ddl_and_audit_is_append_only(db_uri: str) -> None:
    with as_role(db_uri, "tl_api_rw") as c:
        seed(c)
        c.execute("update tl.boards set name = 'B2' where id = 1")
        c.execute("insert into tl.audit_events (id, kind) values (1, 'sign_in')")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("update tl.audit_events set kind = 'x'")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("delete from tl.audit_events")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("create table tl.evil (id int)")


def test_worker_forms_is_limited_to_item_create(db_uri: str) -> None:
    with as_role(db_uri, "tl_api_rw") as c:
        seed(c)
    with as_role(db_uri, "tl_worker_forms") as c:
        c.execute("select id from tl.columns where board_id = 1")
        c.execute(
            "insert into tl.items (id, board_id, group_id, name, position, created_by_type) values (100, 1, 1, 'Lead', 'a', 'form')"
        )
        c.execute("insert into tl.recompute_pending (item_id, requested_seq) values (100, 1)")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("delete from tl.items where id = 100")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("update tl.boards set name = 'x'")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("select * from tl.audit_events")


def test_audit_writer_only_inserts_audit(db_uri: str) -> None:
    with as_role(db_uri, "tl_audit_writer") as c:
        c.execute("insert into tl.audit_events (id, kind) values (2, 'k')")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("select count(*) from tl.items")


def test_tables_are_owned_by_migrator(db_uri: str) -> None:
    with psycopg.connect(db_uri) as c:
        owners = {
            r[0] for r in c.execute("select tableowner from pg_tables where schemaname = 'tl'").fetchall()
        }
    assert owners == {"tl_migrator"}
