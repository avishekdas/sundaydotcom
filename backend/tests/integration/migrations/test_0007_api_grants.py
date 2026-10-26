"""0007: least privilege for the api role (M0B-8, 07 §7.3). The grant table below IS the specification: a new table
gets no access until a migration grants it and this table says so (default privileges no longer give tl_api_rw
everything). perm_epoch moves only through tl.bump_perm_epoch(); account updates are limited to settings columns."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import errors

pytestmark = pytest.mark.integration

SEL, INS, UPD, DEL = "SELECT", "INSERT", "UPDATE", "DELETE"
API_RW: dict[str, set[str]] = {
    "account": {SEL},  # + column-level UPDATE below
    "activity_log": {SEL, INS},
    "board_changes": {SEL, INS},
    "board_members": {SEL, INS, UPD, DEL},
    "boards": {SEL, INS, UPD},
    "columns": {SEL, INS, UPD},
    "groups": {SEL, INS, UPD},
    "idempotency_keys": {SEL, INS, UPD, DEL},
    "item_links": {SEL, INS, DEL},
    "item_text": {SEL, INS, UPD, DEL},
    "items": {SEL, INS, UPD},
    "jobs": {SEL, INS},
    "outbox": {INS},
    "recompute_pending": {SEL, INS, UPD},
    "users": {SEL, INS, UPD, DEL},
    "view_item_positions": {SEL, INS, UPD, DEL},
    "views": {SEL, INS, UPD, DEL},
    "workspace_members": {SEL, INS, UPD, DEL},
    "workspaces": {SEL, INS, UPD},
}
ACCOUNT_UPDATABLE = {
    "name",
    "timezone",
    "date_format",
    "week_start",
    "allowed_domains",
    "logo_file_id",
    "require_mfa",
}


def _grants(c: psycopg.Connection, role: str) -> dict[str, set[str]]:
    rows = c.execute(
        """select table_name, privilege_type from information_schema.role_table_grants
           where grantee = %s and table_schema = 'tl' and privilege_type in ('SELECT','INSERT','UPDATE','DELETE')""",
        (role,),
    ).fetchall()
    out: dict[str, set[str]] = {}
    for table, priv in rows:
        if not table[
            -1
        ].isdigit():  # skip partitions (board_changes_20261026 …): they inherit from the parent
            out.setdefault(table, set()).add(priv)
    return out


def test_api_rw_grants_match_the_table(fresh_db: str) -> None:
    with psycopg.connect(fresh_db) as c:
        assert _grants(c, "tl_api_rw") == API_RW
        cols = {
            r[0]
            for r in c.execute(
                """select column_name from information_schema.column_privileges
               where grantee = 'tl_api_rw' and table_schema = 'tl' and table_name = 'account'
                 and privilege_type = 'UPDATE'"""
            ).fetchall()
        }
        assert cols == ACCOUNT_UPDATABLE


def test_new_tables_get_nothing_by_default(fresh_db: str) -> None:
    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute("set role tl_migrator")
        c.execute("create table tl.later_table (id int)")
        c.execute("reset role")
        assert "later_table" not in _grants(c, "tl_api_rw")


def test_epoch_moves_only_through_the_function(fresh_db: str) -> None:
    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute("set role tl_api_rw")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("update tl.account set perm_epoch = perm_epoch + 1")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("update tl.account set db_generation = 99")
        before = c.execute("select perm_epoch from tl.account").fetchone()
        c.execute("select tl.bump_perm_epoch()")
        after = c.execute("select perm_epoch from tl.account").fetchone()
        assert before and after and after[0] == before[0] + 1
        c.execute("update tl.account set name = 'Acme'")  # settings columns stay writable
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("delete from tl.board_changes")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("delete from tl.activity_log")
