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
