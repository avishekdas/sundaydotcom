"""Realtime registry and fan-out (arch 05 §5.2; AR-10, D-018, D-020).

Clients get a single-use 30 s ticket over HTTPS, open the WebSocket with it, then subscribe to boards.
The fan-out λ receives bus events and posts a shaped message to every connection subscribed to the board.
Skeleton: shaping = changed values only (per-subscriber permission shaping arrives with VisibleItems in M1).
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any, Protocol

from tasklane.platform.clock import Clock

TICKET_TTL = timedelta(seconds=30)
SUBSCRIPTION_TTL = timedelta(hours=2)


class Registry(Protocol):
    def issue_ticket(self, user_id: int) -> str: ...
    def redeem_ticket(self, ticket: str) -> int | None: ...
    def connect(self, connection_id: str, user_id: int) -> None: ...
    def disconnect(self, connection_id: str) -> None: ...
    def subscribe(self, connection_id: str, board_id: int) -> None: ...
    def subscribers(self, board_id: int) -> list[str]: ...
    def user_of(self, connection_id: str) -> int | None: ...


class Gateway(Protocol):
    def send(self, connection_id: str, message: dict[str, Any]) -> bool:
        """Post to one connection; False when it is gone."""
        ...


class InMemoryRegistry:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._tickets: dict[str, tuple[int, float]] = {}
        self._conns: dict[str, int] = {}
        self._subs: dict[int, set[str]] = {}

    def issue_ticket(self, user_id: int) -> str:
        t = secrets.token_urlsafe(32)
        self._tickets[t] = (user_id, (self._clock.now() + TICKET_TTL).timestamp())
        return t

    def redeem_ticket(self, ticket: str) -> int | None:
        entry = self._tickets.pop(ticket, None)
        if entry is None or entry[1] < self._clock.now().timestamp():
            return None
        return entry[0]

    def connect(self, connection_id: str, user_id: int) -> None:
        self._conns[connection_id] = user_id

    def disconnect(self, connection_id: str) -> None:
        self._conns.pop(connection_id, None)
        for subs in self._subs.values():
            subs.discard(connection_id)

    def subscribe(self, connection_id: str, board_id: int) -> None:
        self._subs.setdefault(board_id, set()).add(connection_id)

    def subscribers(self, board_id: int) -> list[str]:
        return sorted(self._subs.get(board_id, set()))

    def user_of(self, connection_id: str) -> int | None:
        return self._conns.get(connection_id)


class DynamoRegistry:
    """Single table: pk/sk/ttl. ticket#T|t, conn#C|c (user), board#B|conn#C and conn#C|board#B (cleanup)."""

    def __init__(self, client: Any, table: str, clock: Clock) -> None:
        self._db = client
        self._t = table
        self._clock = clock

    def _ttl(self, delta: timedelta) -> str:
        return str(int((self._clock.now() + delta).timestamp()))

    def issue_ticket(self, user_id: int) -> str:
        t = secrets.token_urlsafe(32)
        self._db.put_item(
            TableName=self._t,
            Item={
                "pk": {"S": f"ticket#{t}"},
                "sk": {"S": "t"},
                "user": {"N": str(user_id)},
                "ttl": {"N": self._ttl(TICKET_TTL)},
            },
        )
        return t

    def redeem_ticket(self, ticket: str) -> int | None:
        try:
            res = self._db.delete_item(
                TableName=self._t,
                Key={"pk": {"S": f"ticket#{ticket}"}, "sk": {"S": "t"}},
                ConditionExpression="attribute_exists(pk) AND #ttl >= :now",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={":now": {"N": str(int(self._clock.now().timestamp()))}},
                ReturnValues="ALL_OLD",
            )
        except self._db.exceptions.ConditionalCheckFailedException:
            return None
        return int(res["Attributes"]["user"]["N"])

    def connect(self, connection_id: str, user_id: int) -> None:
        self._db.put_item(
            TableName=self._t,
            Item={
                "pk": {"S": f"conn#{connection_id}"},
                "sk": {"S": "c"},
                "user": {"N": str(user_id)},
                "ttl": {"N": self._ttl(SUBSCRIPTION_TTL)},
            },
        )

    def disconnect(self, connection_id: str) -> None:
        res = self._db.query(
            TableName=self._t,
            KeyConditionExpression="pk = :p",
            ExpressionAttributeValues={":p": {"S": f"conn#{connection_id}"}},
        )
        for item in res.get("Items", []):
            sk = item["sk"]["S"]
            self._db.delete_item(
                TableName=self._t, Key={"pk": {"S": f"conn#{connection_id}"}, "sk": {"S": sk}}
            )
            if sk.startswith("board#"):
                self._db.delete_item(
                    TableName=self._t, Key={"pk": {"S": sk}, "sk": {"S": f"conn#{connection_id}"}}
                )

    def subscribe(self, connection_id: str, board_id: int) -> None:
        ttl = {"N": self._ttl(SUBSCRIPTION_TTL)}
        self._db.put_item(
            TableName=self._t,
            Item={"pk": {"S": f"board#{board_id}"}, "sk": {"S": f"conn#{connection_id}"}, "ttl": ttl},
        )
        self._db.put_item(
            TableName=self._t,
            Item={"pk": {"S": f"conn#{connection_id}"}, "sk": {"S": f"board#{board_id}"}, "ttl": ttl},
        )

    def subscribers(self, board_id: int) -> list[str]:
        now = str(int(self._clock.now().timestamp()))
        out: list[str] = []
        kw: dict[str, Any] = {
            "TableName": self._t,
            "KeyConditionExpression": "pk = :p",
            "FilterExpression": "#ttl >= :now",
            "ExpressionAttributeNames": {"#ttl": "ttl"},
            "ExpressionAttributeValues": {":p": {"S": f"board#{board_id}"}, ":now": {"N": now}},
        }
        while True:
            res = self._db.query(**kw)
            out.extend(i["sk"]["S"].removeprefix("conn#") for i in res.get("Items", []))
            if "LastEvaluatedKey" not in res:
                return out
            kw["ExclusiveStartKey"] = res["LastEvaluatedKey"]

    def user_of(self, connection_id: str) -> int | None:
        res = self._db.get_item(
            TableName=self._t, Key={"pk": {"S": f"conn#{connection_id}"}, "sk": {"S": "c"}}
        )
        item = res.get("Item")
        return int(item["user"]["N"]) if item else None


class ApiGatewayGateway:
    def __init__(self, client: Any) -> None:
        self._c = client

    def send(self, connection_id: str, message: dict[str, Any]) -> bool:
        import json

        try:
            self._c.post_to_connection(ConnectionId=connection_id, Data=json.dumps(message).encode())
        except self._c.exceptions.GoneException:
            return False
        return True


def shape(detail: dict[str, Any]) -> dict[str, Any]:
    p = detail.get("payload", {})
    return {
        "type": detail["type"],
        "event_id": detail["event_id"],
        "board_id": str(detail["board_id"]),
        "item_id": str(detail["item_id"]),
        "version": p.get("version"),
        "seq": p.get("seq"),
        "mutation_id": p.get("mutation_id"),
        "values": {c["col"]: c["new"] for c in p.get("changes", [])},
    }


def fan_out(registry: Registry, gateway: Gateway, detail: dict[str, Any]) -> int:
    if detail.get("board_id") is None:
        return 0
    msg = shape(detail)
    sent = 0
    for conn in registry.subscribers(int(detail["board_id"])):
        if gateway.send(conn, msg):
            sent += 1
        else:
            registry.disconnect(conn)
    return sent
