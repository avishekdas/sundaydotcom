"""Migration policy (PE-4): expand/contract discipline, concurrent indexes outside transactions."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tasklane.platform.migrations import discover
from tasklane.platform.sql_script import split_statements

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
DESTRUCTIVE = re.compile(
    r"\b(drop\s+(table|column|index|type|function)|rename\s+(to|column)|alter\s+column\s+\w+\s+(type|set\s+not\s+null))\b",
    re.IGNORECASE,
)
BASELINE = {"0000", "0001", "0002", "0003", "0004"}  # applied before this policy existed; reviewed by hand


def _code(stmt: str) -> str:
    return re.sub(r"--[^\n]*", "", re.sub(r"\$\$.*?\$\$", "", stmt, flags=re.DOTALL))


@pytest.mark.parametrize("mig", discover(MIGRATIONS), ids=lambda m: m.path.name)
def test_destructive_ddl_only_in_contract_migrations(mig) -> None:  # type: ignore[no-untyped-def]
    if mig.version in BASELINE:
        return
    destructive = [s for s in split_statements(mig.sql) if DESTRUCTIVE.search(_code(s))]
    if destructive:
        assert "-- phase: contract" in mig.sql, (
            f"{mig.path.name}: destructive DDL needs '-- phase: contract' and must ship in a later release than the "
            f"code that stopped using the object (expand → migrate → contract): {destructive[0][:80]}"
        )


@pytest.mark.parametrize("mig", discover(MIGRATIONS), ids=lambda m: m.path.name)
def test_indexes_on_existing_tables_are_concurrent_and_outside_a_transaction(mig) -> None:  # type: ignore[no-untyped-def]
    if mig.version in BASELINE:
        return
    for s in split_statements(mig.sql):
        if re.match(r"\s*create\s+(unique\s+)?index\b", _code(s), re.IGNORECASE):
            assert re.search(r"\bconcurrently\b", s, re.IGNORECASE), (
                f"{mig.path.name}: use CREATE INDEX CONCURRENTLY"
            )
            assert "-- run-mode: no-transaction" in mig.sql, (
                f"{mig.path.name}: concurrent index needs no-transaction mode"
            )


ONLY_INDEXES = re.compile(
    r"^\s*(create\s+(unique\s+)?index\s+concurrently|drop\s+index\s+concurrently)\b", re.IGNORECASE
)


@pytest.mark.parametrize("mig", discover(MIGRATIONS), ids=lambda m: m.path.name)
def test_no_transaction_files_hold_only_concurrent_index_statements(mig) -> None:  # type: ignore[no-untyped-def]
    """M0B-10: without a transaction there is no SET LOCAL lock_timeout / role, so only index builds may run there
    (indexes are owned by their table's owner, so the migrator role is not needed)."""
    if not mig.no_transaction:
        return
    for s in split_statements(mig.sql):
        assert ONLY_INDEXES.match(_code(s)), (
            f"{mig.path.name}: only CREATE/DROP INDEX CONCURRENTLY here: {s[:60]}"
        )
