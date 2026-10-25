from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from tasklane.platform.migrations import apply_migrations

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


@pytest.fixture
def fresh_db(pg_uri: str) -> Iterator[str]:
    """A new, fully migrated database per test."""
    name = "t_" + uuid.uuid4().hex[:10]
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"create database {name}")
    uri = make_conninfo(pg_uri, dbname=name)
    apply_migrations(uri, MIGRATIONS)
    yield uri


STATUS = {
    "labels": [
        {"id": 0, "text": "Working on it", "color": "orange"},
        {"id": 1, "text": "Done", "color": "green"},
        {"id": 2, "text": "Stuck", "color": "red"},
    ]
}


@pytest.fixture
def board_db(fresh_db: str) -> str:
    """Workspace 1, board 10 (groups 100 'Active', 101 'Done'), board 20, columns status/owner_text/amount, 3 items."""
    import json

    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute(
            "insert into tl.users (id, email, name, role, status, cognito_sub) values "
            "(42, 'a@example.com', 'Ada', 'admin', 'active', '00000000-0000-0000-0000-000000000042')"
        )
        c.execute("insert into tl.workspaces (id, name, kind, position) values (1, 'Main', 'open', 'a')")
        for b in (10, 20):
            c.execute(
                "insert into tl.boards (id, workspace_id, name, kind, position) values (%s, 1, %s, 'main', 'a')",
                (b, f"Board {b}"),
            )
        c.execute(
            "insert into tl.groups (id, board_id, title, color, position) values "
            "(100, 10, 'Active', 'blue', 'a'), (101, 10, 'Done', 'green', 'b'), (200, 20, 'G', 'blue', 'a')"
        )
        c.execute(
            "insert into tl.columns (board_id, id, title, type, settings, position) values "
            "(10, 'status', 'Status', 'status', %s, 'a'), (10, 'note', 'Note', 'text', '{}', 'b'), "
            "(10, 'amount', 'Amount', 'numbers', '{}', 'c')",
            (json.dumps(STATUS),),
        )
        c.execute("""insert into tl.items (id, board_id, group_id, name, position, created_by_type) values
                     (1001, 10, 101, 'Done thing', 'a', 'user'), (1002, 10, 100, 'Second', 'b', 'user'),
                     (1003, 10, 100, 'First', 'a', 'user'), (2001, 20, 200, 'Other board', 'a', 'user')""")
    return fresh_db
