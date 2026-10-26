"""Forward-only SQL migration runner on the ``Db`` port (PsycopgDb locally, DataApiDb in the migrate λ).

Files are ``NNNN_name.sql`` in one directory, applied in order. Each file runs in its own transaction,
statement by statement (the Data API runs one statement per call, M0A-6), together with its
``tl.schema_migrations`` row. A transaction-scoped advisory lock serialises concurrent runners and the
applied set is re-read under the lock. A file whose first line is ``-- run-as: admin`` runs as the
connecting (administrative) user; every other file runs under ``SET LOCAL ROLE tl_migrator`` so objects
are owned by the migrator role and get its default privileges. Applied files are immutable (checksum).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tasklane.platform.db import Db, PsycopgDb
from tasklane.platform.sql_script import split_statements

_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
_ADMIN = "-- run-as: admin"
LOCK_KEY = 7_115_220_001  # pg_advisory_xact_lock key for "tasklane migrations"
LOGIN_ROLES = frozenset(
    {
        "tl_migrator",
        "tl_api_rw",
        "tl_reader",
        "tl_worker",
        "tl_worker_outbox",
        "tl_worker_forms",
        "tl_audit_writer",
    }
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
    def no_transaction(self) -> bool:
        """``-- run-mode: no-transaction`` (CREATE INDEX CONCURRENTLY): statements run one by one, autocommit."""
        return any(line.strip() == "-- run-mode: no-transaction" for line in self.sql.splitlines()[:3])

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
        if mig.no_transaction:
            if mig.version not in _applied(db):
                # Each statement autocommits (no SET LOCAL lock_timeout / role), so these files hold only
                # CREATE/DROP INDEX CONCURRENTLY (policy test) — an index belongs to its table's owner. A lease row
                # keeps a second runner (pipeline + manual invoke) out; the Data API cannot hold an advisory lock
                # across calls (M0B-10). Statements must be idempotent (IF NOT EXISTS); an invalid index from a
                # failed run is dropped by hand before re-running (runbook: ops/runbooks/migrations.md).
                holder = _take_lease(db)
                try:
                    if mig.version not in _applied(db):
                        for stmt in split_statements(mig.sql):
                            db.execute(stmt)
                        with db.transaction() as tx:
                            tx.execute(
                                "insert into tl.schema_migrations (version, name, checksum) values (:v, :n, :c) "
                                "on conflict (version) do nothing",
                                {"v": mig.version, "n": mig.path.stem, "c": mig.checksum},
                            )
                        done.append(mig.version)
                finally:
                    _release_lease(db, holder)
            continue
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


LEASE = "migrations"


def _take_lease(db: Db) -> str:
    holder = str(uuid.uuid4())
    rows = db.query(
        """insert into tl.leases (name, holder, until) values (:n, :h, now() + interval '15 minutes')
           on conflict (name) do update set holder = excluded.holder, until = excluded.until
             where tl.leases.until < now()
           returning name""",
        {"n": LEASE, "h": holder},
    )
    if not rows:
        raise RuntimeError("another migration run holds the lease; retry when it has finished")
    return holder


def _release_lease(db: Db, holder: str) -> None:
    db.execute(
        "update tl.leases set until = now() - interval '1 second' where name = :n and holder = :h",
        {"n": LEASE, "h": holder},
    )


def scram_verifier(password: str, *, salt: bytes | None = None, iterations: int = 4096) -> str:
    """PostgreSQL's SCRAM-SHA-256 verifier (RFC 5802/7677): what the server stores instead of the password."""
    salt = salt if salt is not None else secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", "sha256").digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", "sha256").digest()
    salt_b64, stored_b64, server_b64 = (base64.b64encode(b).decode() for b in (salt, stored_key, server_key))
    return f"SCRAM-SHA-256${iterations}:{salt_b64}${stored_b64}:{server_b64}"


def role_password_sql(role: str, password: str) -> str:
    """``ALTER ROLE … PASSWORD '<verifier>'``: the plaintext never reaches SQL, logs or pg_stat_statements (M0B-14)."""
    if role not in LOGIN_ROLES:
        raise ValueError(f"unknown role {role!r}")
    if not password or "\x00" in password:
        raise ValueError(f"empty or invalid password for {role}")
    return f"alter role \"{role}\" login password '{scram_verifier(password)}'"


def ensure_role_logins(db: Db, passwords: Mapping[str, str]) -> None:
    """Give each function-class role LOGIN and the password from its secret (M0A-3), as a SCRAM verifier."""
    for role, password in passwords.items():
        db.execute(role_password_sql(role, password))
