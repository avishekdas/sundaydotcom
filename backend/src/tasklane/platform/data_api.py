"""RDS Data API adapter for the ``Db`` port (ADR-002).

Values come back from ``formatRecordsAs=JSON``: numbers as JSON numbers, everything else (timestamps,
numeric, jsonb) as strings — callers decode what they need. An auto-paused Serverless v2 cluster answers
``DatabaseResumingException`` for up to ~30 s; calls are retried with backoff (M0A-9).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from tasklane.platform.db import DataApiRuleViolation, Json, Params, Row, validate_params, validate_sql


class DatabaseResuming(RuntimeError):
    """The cluster is still resuming from auto-pause after all retries."""


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        return code if isinstance(code, str) else None
    return None


def encode_param(name: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    if isinstance(value, str):
        return {"name": name, "value": {"stringValue": value}}
    if isinstance(value, Decimal):
        return {"name": name, "value": {"stringValue": str(value)}, "typeHint": "DECIMAL"}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise DataApiRuleViolation(f"parameter {name!r}: naive datetime; pass an aware UTC datetime")
        text = value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
        return {"name": name, "value": {"stringValue": text}, "typeHint": "TIMESTAMP"}
    if isinstance(value, date):
        return {"name": name, "value": {"stringValue": value.isoformat()}, "typeHint": "DATE"}
    if isinstance(value, Json):
        return {"name": name, "value": {"stringValue": value.dumps()}, "typeHint": "JSON"}
    raise DataApiRuleViolation(f"parameter {name!r}: unsupported type {type(value).__name__}")


class DataApiDb:
    def __init__(
        self,
        client: Any,
        *,
        resource_arn: str,
        secret_arn: str,
        database: str,
        transaction_id: str | None = None,
        resume_attempts: int = 5,  # 1+2+4+8 s of backoff: fits the 29 s api timeout (M0B-15)
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._base = {"resourceArn": resource_arn, "secretArn": secret_arn, "database": database}
        self._tx = transaction_id
        self._attempts = resume_attempts
        self._sleep = sleep

    def _call(self, op: str, **kw: Any) -> dict[str, Any]:
        base = (
            self._base
            if op in ("execute_statement", "begin_transaction")
            else {k: v for k, v in self._base.items() if k != "database"}
        )  # commit/rollback take no database
        delay = 1.0
        for attempt in range(self._attempts):
            try:
                result: dict[str, Any] = getattr(self._client, op)(**base, **kw)
                return result
            except Exception as exc:
                if _error_code(exc) != "DatabaseResumingException":
                    raise
                if attempt == self._attempts - 1:
                    raise DatabaseResuming("Aurora cluster is still resuming from auto-pause") from exc
                self._sleep(delay)
                delay = min(delay * 2, 8.0)
        raise AssertionError("unreachable")

    def _execute(self, sql: str, params: Params | None) -> dict[str, Any]:
        validate_sql(sql)
        validate_params(sql, params)
        kw: dict[str, Any] = {"sql": sql, "formatRecordsAs": "JSON"}
        if params:
            kw["parameters"] = [encode_param(k, v) for k, v in params.items()]
        if self._tx:
            kw["transactionId"] = self._tx
        return self._call("execute_statement", **kw)

    def query(self, sql: str, params: Params | None = None) -> list[Row]:
        rows: list[Row] = json.loads(self._execute(sql, params).get("formattedRecords") or "[]")
        return rows

    def execute(self, sql: str, params: Params | None = None) -> int:
        return int(self._execute(sql, params).get("numberOfRecordsUpdated", 0))

    @contextmanager
    def transaction(self) -> Iterator[DataApiDb]:
        if self._tx:
            raise RuntimeError("nested transactions are not supported by the Data API")
        tx = self._call("begin_transaction")["transactionId"]
        inner = DataApiDb(
            self._client,
            resource_arn=self._base["resourceArn"],
            secret_arn=self._base["secretArn"],
            database=self._base["database"],
            transaction_id=tx,
            resume_attempts=self._attempts,
            sleep=self._sleep,
        )
        try:
            yield inner
        except BaseException:
            self._call("rollback_transaction", transactionId=tx)
            raise
        self._call("commit_transaction", transactionId=tx)
