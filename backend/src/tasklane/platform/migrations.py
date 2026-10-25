"""Forward-only SQL migration runner on the ``Db`` port (PsycopgDb locally, DataApiDb in the migrate λ).

Files are ``NNNN_name.sql`` in one directory, applied in order. Each file runs in its own transaction,
statement by statement (the Data API runs one statement per call, M0A-6), together with its
``tl.schema_migrations`` row. A transaction-scoped advisory lock serialises concurrent runners and the
applied set is re-read under the lock. A file whose first line is ``-- run-as: admin`` runs as the
connecting (administrative) user; every other file runs under ``SET LOCAL ROLE tl_migrator`` so objects
are owned by the migrator role and get its default privileges. Applied files are immutable (checksum).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tasklane.platform.db import Db, PsycopgDb
from tasklane.platform.sql_script import split_statements

_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_ADMIN = "-- run-as: admin"
LOCK_KEY = 7_115_220_001  # pg_advisory_xact_lock key for "tasklane migrations"
LOGIN_ROLES = frozenset(
    {"tl_migrator", "tl_api_rw", "tl_reader", "tl_worker", "tl_worker_forms", "tl_audit_writer"}
)


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


def _applied(db: Db) -> dict[str, str]:
    rows = db.query("select to_regclass('tl.schema_migrations') is not null as present")
    if not rows or not rows[0]["present"]:
        return {}
    return {
        r["version"]: r["checksum"] for r in db.query("select version, checksum from tl.schema_migrations")
    }


def apply_migrations(target: Db | str, directory: Path, *, lock_timeout: str = "5s") -> list[str]:
    """Apply pending migrations; return the versions applied. Raises if an applied file changed."""
    db: Db = PsycopgDb(target) if isinstance(target, str) else target
    migrations = discover(directory)
    if not re.fullmatch(r"\d+(ms|s)", lock_timeout):
        raise ValueError(f"bad lock_timeout {lock_timeout!r}")
    applied = _applied(db)
    for mig in migrations:  # fail fast on edited files before taking any lock
        if mig.version in applied and applied[mig.version] != mig.checksum:
            raise RuntimeError(f"checksum mismatch for applied migration {mig.path.name}")
    done: list[str] = []
    for mig in migrations:
        with db.transaction() as tx:
            tx.execute("select pg_advisory_xact_lock(:k)", {"k": LOCK_KEY})
            applied = _applied(tx)
            if mig.version in applied:
                if applied[mig.version] != mig.checksum:
                    raise RuntimeError(f"checksum mismatch for applied migration {mig.path.name}")
                continue
            tx.execute(f"set local lock_timeout = '{lock_timeout}'")
            if not mig.as_admin:
                tx.execute("set local role tl_migrator")
            for stmt in split_statements(mig.sql):
                tx.execute(stmt)
            tx.execute(
                "insert into tl.schema_migrations (version, name, checksum) values (:v, :n, :c)",
                {"v": mig.version, "n": mig.path.stem, "c": mig.checksum},
            )
        done.append(mig.version)
    return done


def _quote_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def ensure_role_logins(db: Db, passwords: Mapping[str, str]) -> None:
    """Give each function-class role LOGIN and the password from its secret (M0A-3). Idempotent."""
    for role, password in passwords.items():
        if role not in LOGIN_ROLES:
            raise ValueError(f"unknown role {role!r}")
        if not password or "\x00" in password:
            raise ValueError(f"empty or invalid password for {role}")
        db.execute(f'alter role "{role}" login password {_quote_literal(password)}')
