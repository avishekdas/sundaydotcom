"""Forward-only SQL migration runner.

Files are ``NNNN_name.sql`` in one directory, applied in order, each in its own transaction together with
its ``tl.schema_migrations`` row. A file whose first line is ``-- run-as: admin`` runs as the connecting
(administrative) user; every other file runs under ``SET LOCAL ROLE tl_migrator`` so all objects are owned
by the migrator role and pick up its default privileges. Applied files are immutable (checksum).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_ADMIN = "-- run-as: admin"


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()

    @property
    def as_admin(self) -> bool:
        return self.sql.lstrip().startswith(_ADMIN)


def discover(directory: Path) -> list[Migration]:
    found: list[Migration] = []
    for p in sorted(directory.glob("*.sql")):
        m = _NAME.match(p.name)
        if not m:
            raise ValueError(f"bad migration file name: {p.name}")
        found.append(Migration(m.group(1), p, p.read_text()))
    for expected, mig in enumerate(found):
        if int(mig.version) != expected:
            raise ValueError(f"migration gap: expected {expected:04d}, found {mig.version}")
    return found


def _applied(conn: psycopg.Connection) -> dict[str, str]:
    row = conn.execute("select to_regclass('tl.schema_migrations') is not null").fetchone()
    if not row or not row[0]:
        return {}
    return {v: c for v, c in conn.execute("select version, checksum from tl.schema_migrations").fetchall()}


def apply_migrations(uri: str, directory: Path) -> list[str]:
    """Apply pending migrations; return the versions applied. Raises if an applied file changed."""
    migrations = discover(directory)
    done: list[str] = []
    with psycopg.connect(uri, autocommit=True) as conn:
        applied = _applied(conn)
        for mig in migrations:
            if mig.version in applied:
                if applied[mig.version] != mig.checksum:
                    raise RuntimeError(f"checksum mismatch for applied migration {mig.path.name}")
                continue
            with conn.transaction():
                if not mig.as_admin:
                    conn.execute("set local role tl_migrator")
                conn.execute(mig.sql.encode())
                conn.execute(
                    "insert into tl.schema_migrations (version, name, checksum) values (%s, %s, %s)",
                    (mig.version, mig.path.stem, mig.checksum),
                )
            done.append(mig.version)
    return done
