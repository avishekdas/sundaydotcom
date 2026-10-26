"""Rate-limit counters (arch 03 §3.8): fixed windows that open at the first hit and expire as a whole.

`DynamoCounters` keeps one item per key `{pk, n, expires_at}` (epoch seconds; DynamoDB TTL only garbage-collects,
so reads check `expires_at` themselves). `InMemoryCounters` is the fake used by Tier A and local dev.
"""

from __future__ import annotations

import math
from typing import Any, Protocol

from tasklane.platform.clock import Clock


class Counters(Protocol):
    def hit(self, key: str, window_s: int) -> int: ...
    def count(self, key: str) -> int: ...
    def remaining_s(self, key: str) -> int: ...
    def clear(self, key: str) -> None: ...


def _now(clock: Clock) -> float:
    return clock.now().timestamp()


class InMemoryCounters:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._items: dict[str, tuple[int, float]] = {}

    def _live(self, key: str) -> tuple[int, float] | None:
        item = self._items.get(key)
        return item if item and item[1] > _now(self._clock) else None

    def hit(self, key: str, window_s: int) -> int:
        live = self._live(key)
        n, expires = (live[0] + 1, live[1]) if live else (1, _now(self._clock) + window_s)
        self._items[key] = (n, expires)
        return n

    def count(self, key: str) -> int:
        live = self._live(key)
        return live[0] if live else 0

    def remaining_s(self, key: str) -> int:
        live = self._live(key)
        return math.ceil(live[1] - _now(self._clock)) if live else 0

    def clear(self, key: str) -> None:
        self._items.pop(key, None)


class DynamoCounters:
    def __init__(self, client: Any, table: str, clock: Clock) -> None:
        self._c, self._table, self._clock = client, table, clock

    def _get(self, key: str) -> tuple[int, int] | None:
        item = self._c.get_item(TableName=self._table, Key={"pk": {"S": key}}, ConsistentRead=True).get(
            "Item"
        )
        if not item or int(item["expires_at"]["N"]) <= _now(self._clock):
            return None
        return int(item["n"]["N"]), int(item["expires_at"]["N"])

    def hit(self, key: str, window_s: int) -> int:
        now = int(_now(self._clock))
        cond = self._c.exceptions.ConditionalCheckFailedException
        for _ in range(3):  # live window → add; otherwise (re)open one; a lost race retries
            try:
                res = self._c.update_item(
                    TableName=self._table,
                    Key={"pk": {"S": key}},
                    UpdateExpression="ADD n :one",
                    ConditionExpression="expires_at > :now",
                    ExpressionAttributeValues={":one": {"N": "1"}, ":now": {"N": str(now)}},
                    ReturnValues="UPDATED_NEW",
                )
                return int(res["Attributes"]["n"]["N"])
            except cond:
                pass
            try:
                self._c.put_item(
                    TableName=self._table,
                    Item={"pk": {"S": key}, "n": {"N": "1"}, "expires_at": {"N": str(now + window_s)}},
                    ConditionExpression="attribute_not_exists(pk) or expires_at <= :now",
                    ExpressionAttributeValues={":now": {"N": str(now)}},
                )
                return 1
            except cond:
                continue
        raise RuntimeError(f"counter {key!r}: contention")

    def count(self, key: str) -> int:
        live = self._get(key)
        return live[0] if live else 0

    def remaining_s(self, key: str) -> int:
        live = self._get(key)
        return max(0, math.ceil(live[1] - _now(self._clock))) if live else 0

    def clear(self, key: str) -> None:
        self._c.delete_item(TableName=self._table, Key={"pk": {"S": key}})
