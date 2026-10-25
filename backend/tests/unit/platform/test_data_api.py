"""DataApiDb adapter (ADR-002): parameter encoding, JSON records, transactions, resume retry (M0A-9/14)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from tasklane.platform.data_api import DataApiDb, DatabaseResuming
from tasklane.platform.db import DataApiRuleViolation, Json

# Parameter names each rds-data operation accepts (botocore service model) — the fake rejects others.
ALLOWED = {
    "execute_statement": {
        "resourceArn",
        "secretArn",
        "database",
        "sql",
        "parameters",
        "transactionId",
        "formatRecordsAs",
        "includeResultMetadata",
        "continueAfterTimeout",
        "schema",
        "resultSetOptions",
    },
    "begin_transaction": {"resourceArn", "secretArn", "database", "schema"},
    "commit_transaction": {"resourceArn", "secretArn", "transactionId"},
    "rollback_transaction": {"resourceArn", "secretArn", "transactionId"},
}


def _check(op: str, kw: dict[str, Any]) -> None:
    unknown = set(kw) - ALLOWED[op]
    if unknown:
        raise TypeError(f"{op}: unknown parameters {sorted(unknown)}")


class FakeClient:
    def __init__(self, responses: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses = list(responses or [])

    def _next(self, default: dict[str, Any]) -> dict[str, Any]:
        if self.responses:
            r = self.responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r  # type: ignore[no-any-return]
        return default

    def execute_statement(self, **kw: Any) -> dict[str, Any]:
        _check("execute_statement", kw)
        self.calls.append(("execute_statement", kw))
        return self._next({"formattedRecords": "[]", "numberOfRecordsUpdated": 0})

    def begin_transaction(self, **kw: Any) -> dict[str, Any]:
        _check("begin_transaction", kw)
        self.calls.append(("begin_transaction", kw))
        return {"transactionId": "tx-1"}

    def commit_transaction(self, **kw: Any) -> dict[str, Any]:
        _check("commit_transaction", kw)
        self.calls.append(("commit_transaction", kw))
        return {}

    def rollback_transaction(self, **kw: Any) -> dict[str, Any]:
        _check("rollback_transaction", kw)
        self.calls.append(("rollback_transaction", kw))
        return {}


class ResumingError(Exception):
    def __init__(self) -> None:
        super().__init__("resuming")
        self.response = {"Error": {"Code": "DatabaseResumingException"}}


def db(client: FakeClient, **kw: Any) -> DataApiDb:
    return DataApiDb(
        client,
        resource_arn="arn:cluster",
        secret_arn="arn:secret",  # noqa: S106 (an ARN, not a password)
        database="tasklane",
        sleep=lambda _s: None,
        **kw,
    )


def test_parameters_are_encoded_with_type_hints() -> None:
    c = FakeClient()
    db(c).query(
        "select :a, :b, :c, :d, :e, :f, :g, :h",
        {
            "a": 1,
            "b": "x",
            "c": True,
            "d": None,
            "e": Decimal("1.50"),
            "f": date(2026, 1, 2),
            "g": datetime(2026, 1, 2, 3, 4, 5, 600000, tzinfo=UTC),
            "h": Json({"k": [1]}),
        },
    )
    p = {x["name"]: x for x in c.calls[0][1]["parameters"]}
    assert p["a"]["value"] == {"longValue": 1}
    assert p["b"]["value"] == {"stringValue": "x"}
    assert p["c"]["value"] == {"booleanValue": True}
    assert p["d"]["value"] == {"isNull": True}
    assert p["e"] == {"name": "e", "value": {"stringValue": "1.50"}, "typeHint": "DECIMAL"}
    assert p["f"] == {"name": "f", "value": {"stringValue": "2026-01-02"}, "typeHint": "DATE"}
    assert p["g"] == {
        "name": "g",
        "value": {"stringValue": "2026-01-02 03:04:05.600000"},
        "typeHint": "TIMESTAMP",
    }
    assert p["h"] == {"name": "h", "value": {"stringValue": '{"k":[1]}'}, "typeHint": "JSON"}
    assert c.calls[0][1]["formatRecordsAs"] == "JSON"


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(DataApiRuleViolation):
        db(FakeClient()).query("select :t", {"t": datetime(2026, 1, 1)})


def test_rules_are_enforced_before_calling_aws() -> None:
    c = FakeClient()
    with pytest.raises(DataApiRuleViolation):
        db(c).query("select * from t where id = any(:ids)", {"ids": Json([1])})
    assert c.calls == []


def test_query_returns_json_records_and_execute_returns_count() -> None:
    c = FakeClient([{"formattedRecords": json.dumps([{"id": 1}])}, {"numberOfRecordsUpdated": 3}])
    d = db(c)
    assert d.query("select 1 id") == [{"id": 1}]
    assert d.execute("update t set x = 1") == 3


def test_transaction_commits_and_passes_transaction_id() -> None:
    c = FakeClient()
    with db(c).transaction() as tx:
        tx.execute("select 1")
    names = [n for n, _ in c.calls]
    assert names == ["begin_transaction", "execute_statement", "commit_transaction"]
    assert c.calls[1][1]["transactionId"] == "tx-1"


def test_transaction_rolls_back_on_error() -> None:
    c = FakeClient()
    with pytest.raises(RuntimeError), db(c).transaction() as tx:
        tx.execute("select 1")
        raise RuntimeError("boom")
    assert [n for n, _ in c.calls][-1] == "rollback_transaction"


def test_resuming_cluster_is_retried_then_gives_up() -> None:
    c = FakeClient([ResumingError(), ResumingError(), {"formattedRecords": "[]"}])
    assert db(c).query("select 1") == []
    c2 = FakeClient([ResumingError()] * 10)
    with pytest.raises(DatabaseResuming):
        db(c2, resume_attempts=3).query("select 1")
