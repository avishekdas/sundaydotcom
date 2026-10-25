"""Database port (ADR-002).

Every adapter speaks the same dialect: SQL with ``:name`` parameters and Data API-compatible values.
The RDS Data API has no array parameters, a 64 KB row limit and a 1 MiB response limit (arch 03 §3.9);
``StrictDataApiFake`` enforces those rules against a real PostgreSQL so they fail in local tests and CI,
not after deployment (AR-4, AR-21, AR-24).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

ROW_LIMIT_BYTES = 64 * 1024
RESPONSE_LIMIT_BYTES = 1024 * 1024


class DataApiRuleViolation(ValueError):
    """Raised when a statement or parameter would fail (or silently misbehave) on the RDS Data API."""


@dataclass(frozen=True, slots=True)
class Json:
    """Explicit JSON parameter. Containers must be wrapped so sets travel as JSON text (AR-4)."""

    value: Any

    def dumps(self) -> str:
        return json.dumps(self.value, separators=(",", ":"), default=str)


Param = None | bool | int | str | Decimal | date | datetime | Json
Params = Mapping[str, Param]
Row = dict[str, Any]


class Db(Protocol):
    def query(self, sql: str, params: Params | None = None) -> list[Row]: ...
    def execute(self, sql: str, params: Params | None = None) -> int: ...
    def transaction(self) -> Any: ...  # context manager yielding a Db bound to one transaction


# --- SQL text helpers -------------------------------------------------------------------------------

# Tokens we must skip when looking for :params: string literals, quoted identifiers, casts.
_TOKEN = re.compile(
    r"""(?P<str>'(?:[^']|'')*')|(?P<ident>"(?:[^"]|"")*")|(?P<cast>::)|(?P<param>(?<!:):(?P<name>[A-Za-z_][A-Za-z0-9_]*))|(?P<pct>%)""",
)


def _scan(sql: str) -> tuple[str, list[str]]:
    out: list[str] = []
    names: list[str] = []
    pos = 0
    for m in _TOKEN.finditer(sql):
        out.append(sql[pos : m.start()].replace("%", "%%"))
        if m.group("str") is not None:
            out.append(m.group("str").replace("%", "%%"))
        elif m.group("ident") is not None:
            out.append(m.group("ident").replace("%", "%%"))
        elif m.group("cast") is not None:
            out.append("::")
        elif m.group("param") is not None:
            names.append(m.group("name"))
            out.append(f"%({m.group('name')})s")
        else:
            out.append("%%")
        pos = m.end()
    out.append(sql[pos:].replace("%", "%%"))
    return "".join(out), names


def to_pyformat(sql: str) -> str:
    """Translate ``:name`` parameters to psycopg ``%(name)s`` without touching literals or casts."""
    return _scan(sql)[0]


def param_names(sql: str) -> list[str]:
    return _scan(sql)[1]


_ANY_ALL_PARAM = re.compile(r"\b(any|all)\s*\(\s*:[A-Za-z_]", re.IGNORECASE)
_RETURNING_OLD = re.compile(r"\breturning\b[^;]*\bold\s*\.", re.IGNORECASE | re.DOTALL)


def _strip_literals(sql: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def validate_sql(sql: str) -> None:
    body = _strip_literals(sql)
    if _ANY_ALL_PARAM.search(body):
        raise DataApiRuleViolation(
            "any(:param)/all(:param) needs an array parameter, which the Data API does not support; "
            "use `in (select ... from jsonb_array_elements_text(:p::jsonb))` or jsonb containment (PERF-18)"
        )
    if _RETURNING_OLD.search(body):
        raise DataApiRuleViolation(
            "RETURNING old.* is PostgreSQL 18-only syntax; use the pre-image CTE pattern (arch 03 §3.5)"
        )


def validate_params(sql: str, params: Params | None) -> None:
    params = params or {}
    used = set(param_names(sql))
    missing = used - params.keys()
    if missing:
        raise DataApiRuleViolation(f"missing parameters: {sorted(missing)}")
    unused = params.keys() - used
    if unused:
        raise DataApiRuleViolation(f"unused parameters: {sorted(unused)}")
    for name, value in params.items():
        if isinstance(value, bool | int | str | Decimal | date | datetime | Json) or value is None:
            continue
        if isinstance(value, float):
            raise DataApiRuleViolation(f"parameter {name!r}: float loses precision; use Decimal")
        if isinstance(value, list | tuple | set | frozenset | dict):
            raise DataApiRuleViolation(
                f"parameter {name!r}: array/container parameters are not supported by the Data API; "
                "wrap in Json(...)"
            )
        raise DataApiRuleViolation(f"parameter {name!r}: unsupported type {type(value).__name__}")


def _row_bytes(row: Row) -> int:
    return len(json.dumps(row, default=str, separators=(",", ":")).encode())


# --- psycopg adapters ----------------------------------------------------------------------------------


class PsycopgDb:
    """PostgreSQL via psycopg (local development, tests and the RDS Proxy fallback of ADR-002)."""

    def __init__(self, uri: str, *, _conn: Any = None) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._uri = uri
        self._owns = _conn is None
        self._conn = _conn or psycopg.connect(uri, autocommit=True, row_factory=dict_row)

    def _adapt(self, params: Params | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in (params or {}).items():
            out[k] = v.dumps() if isinstance(v, Json) else v
        return out

    def _run(self, sql: str, params: Params | None) -> Any:
        return self._conn.execute(to_pyformat(sql), self._adapt(params))

    def query(self, sql: str, params: Params | None = None) -> list[Row]:
        return list(self._run(sql, params).fetchall())

    def execute(self, sql: str, params: Params | None = None) -> int:
        return int(self._run(sql, params).rowcount)

    @contextmanager
    def transaction(self) -> Iterator[PsycopgDb]:
        with self._conn.transaction():
            yield type(self)(self._uri, _conn=self._conn)

    def close(self) -> None:
        if self._owns:
            self._conn.close()


class StrictDataApiFake(PsycopgDb):
    """PsycopgDb that enforces RDS Data API semantics (AR-24): run on every PR."""

    def _check(self, sql: str, params: Params | None) -> None:
        validate_sql(sql)
        validate_params(sql, params)

    def _adapt(self, params: Params | None) -> dict[str, Any]:
        """Type parameters the way the Data API does: integers are longValue (int8), text is text."""
        from psycopg.types.numeric import Int8

        out = super()._adapt(params)
        return {k: Int8(v) if isinstance(v, int) and not isinstance(v, bool) else v for k, v in out.items()}

    def query(self, sql: str, params: Params | None = None) -> list[Row]:
        self._check(sql, params)
        cur = self._run(sql, params)
        rows = [_as_data_api_row(r, cur.description or [], self._conn) for r in cur.fetchall()]
        total = 0
        for row in rows:
            size = _row_bytes(row)
            if size > ROW_LIMIT_BYTES:
                raise DataApiRuleViolation(f"row of {size} bytes exceeds the Data API 64 KB row limit")
            total += size
            if total > RESPONSE_LIMIT_BYTES:
                raise DataApiRuleViolation(
                    "result exceeds the Data API 1 MiB response limit; page or project less"
                )
        return rows

    def execute(self, sql: str, params: Params | None = None) -> int:
        self._check(sql, params)
        return super().execute(sql, params)


# --- Data API result shapes (formatRecordsAs=JSON), observed on Aurora PG 18.6 (M0A-14) ---------------------

_JSON_OIDS = {114, 3802}  # json, jsonb → JSON text
_TEXTUAL_OIDS = {1700, 2950, 869}  # numeric, uuid, inet → string
_UNSUPPORTED_OIDS = {1186: "interval", 5069: "xid8"}
_TYPE_NAMES: dict[int, str] = {}


def _type_name(conn: Any, oid: int) -> str:
    if oid not in _TYPE_NAMES:
        row = conn.execute("select typname from pg_type where oid = %s", (oid,)).fetchone()
        _TYPE_NAMES[oid] = (row["typname"] if isinstance(row, dict) else row[0]) if row else ""
    return _TYPE_NAMES[oid]


def _as_data_api_value(v: Any, oid: int, conn: Any) -> Any:
    if oid in _UNSUPPORTED_OIDS or _type_name(conn, oid) == "citext":
        name = _UNSUPPORTED_OIDS.get(oid, "citext")
        raise DataApiRuleViolation(
            f"the Data API returns UnsupportedResultException for {name}; cast it (e.g. ::text)"
        )
    if v is None:
        return None
    if oid in _JSON_OIDS:
        return json.dumps(v, separators=(",", ":"), default=str)
    if oid == 869:  # inet: the Data API renders the prefix length
        text = str(v)
        return text if "/" in text else f"{text}/{32 if ':' not in text else 128}"
    if oid in _TEXTUAL_OIDS:
        return str(v)
    if isinstance(v, datetime):
        from datetime import UTC

        naive = v.astimezone(UTC).replace(tzinfo=None) if v.tzinfo else v
        return naive.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def _as_data_api_row(row: Row, description: Any, conn: Any) -> Row:
    return {col.name: _as_data_api_value(row[col.name], col.type_code, conn) for col in description}
