"""Skeleton HTTP API (arch 04): routing, auth context from the JWT authorizer, error shape, publish after commit."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from tasklane.api.app import Deps, handle
from tasklane.collab.realtime import InMemoryRegistry
from tasklane.platform.clock import FakeClock
from tasklane.platform.db import StrictDataApiFake

pytestmark = pytest.mark.integration
ADA_SUB = "00000000-0000-0000-0000-000000000042"


class Pub:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        self.entries.extend(entries)
        return []


def call(deps: Deps, method: str, path: str, body: Any = None, sub: str | None = ADA_SUB) -> tuple[int, Any]:
    event: dict[str, Any] = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "http": {"method": method, "path": path, "sourceIp": "1.2.3.4"},
            "stage": "$default",
            "requestId": "req-1",
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }
    if sub:
        event["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": sub}, "scopes": None}}
    res = handle(event, deps)
    return res["statusCode"], json.loads(res["body"]) if res.get("body") else None


@pytest.fixture
def deps(board_db: str) -> Deps:
    clock = FakeClock(datetime(2026, 10, 25, 12, tzinfo=UTC))
    return Deps(
        db=StrictDataApiFake(board_db),
        publisher=Pub(),
        registry=InMemoryRegistry(clock),
        clock=clock,
        ws_url="wss://ws.example/dev",
        bus_name="tasklane-test",
    )


def test_unauthenticated_and_unknown_users_get_401(deps: Deps) -> None:
    assert call(deps, "GET", "/api/v1/me", sub=None)[0] == 401
    status, body = call(deps, "GET", "/api/v1/me", sub="00000000-0000-0000-0000-00000000dead")
    assert status == 401 and body["error"]["code"] == "unauthenticated"


def test_me(deps: Deps) -> None:
    assert call(deps, "GET", "/api/v1/me") == (
        200,
        {
            "id": "42",
            "name": "Ada",
            "email": "a@example.com",
            "title": None,
            "phone": None,
            "timezone": None,
            "effective_timezone": "UTC",
            "role": "admin",
            "capabilities": ["create_board", "create_workspace", "export", "invite", "manage_account"],
        },
    )


def test_schema_query_fetch(deps: Deps) -> None:
    status, schema = call(deps, "GET", "/api/v1/boards/10/schema")
    assert status == 200 and [c["id"] for c in schema["columns"]] == ["status", "note", "amount"]
    assert call(deps, "GET", "/api/v1/boards/999/schema")[0] == 404
    status, q = call(deps, "POST", "/api/v1/boards/10/query", {})
    assert status == 200 and q["ids"] == ["1003", "1002", "1001"]
    status, rows = call(deps, "POST", "/api/v1/boards/10/items:fetch", {"ids": ["1003"]})
    assert status == 200 and rows["items"][0]["name"] == "First"


def test_patch_values_publishes_after_commit_and_validates(deps: Deps) -> None:
    status, body = call(
        deps, "PATCH", "/api/v1/items/1003/values", {"values": {"status": {"l": 1}}, "mutation_id": "m1"}
    )
    assert status == 200 and body == {
        "id": "1003",
        "version": 2,
        "values": {"status": {"l": 1}},
        "computed_pending": True,
    }
    entries = deps.publisher.entries  # type: ignore[attr-defined]
    assert len(entries) == 1 and entries[0]["DetailType"] == "item.values_changed"
    status, body = call(deps, "PATCH", "/api/v1/items/1003/values", {"values": {"status": {"l": 99}}})
    assert (
        status == 400
        and body["error"]["code"] == "validation_error"
        and "values.status" in body["error"]["fields"]
    )
    assert call(deps, "PATCH", "/api/v1/items/999/values", {"values": {"note": "x"}})[0] == 404


def test_changes_cursor_round_trip(deps: Deps) -> None:
    _, start = call(deps, "POST", "/api/v1/boards/10/changes", {})
    call(deps, "PATCH", "/api/v1/items/1002/values", {"values": {"note": "x"}})
    _, ch = call(deps, "POST", "/api/v1/boards/10/changes", {"since_xmin": start["next_since_xmin"]})
    assert [c["item_id"] for c in ch["changes"]] == ["1002"] and ch["db_generation"] == 1


def test_realtime_ticket(deps: Deps) -> None:
    status, body = call(deps, "POST", "/api/v1/realtime/ticket", {})
    assert status == 200 and body["url"] == "wss://ws.example/dev"
    assert deps.registry.redeem_ticket(body["ticket"]) == 42


def test_unknown_route_is_404_with_error_shape(deps: Deps) -> None:
    status, body = call(deps, "GET", "/api/v1/nope")
    assert status == 404 and body["error"]["code"] == "not_found"


def test_fault_injection_only_outside_prod(
    deps: Deps, monkeypatch: pytest.MonkeyPatch
) -> None:  # canary rehearsal
    from tasklane.api import app as api_app

    monkeypatch.setenv("TL_FAULT_INJECTION", "1")
    monkeypatch.setenv("STAGE", "dev")
    with pytest.raises(RuntimeError, match="fault injection"):
        api_app.handler({"rawPath": "/api/v1/me"}, None)
    monkeypatch.setenv("STAGE", "prod")
    monkeypatch.setattr(api_app, "_env_deps", lambda: deps)
    assert (
        api_app.handler(
            {
                "version": "2.0",
                "routeKey": "GET /api/v1/me",
                "rawPath": "/api/v1/me",
                "rawQueryString": "",
                "headers": {},
                "requestContext": {
                    "http": {"method": "GET", "path": "/api/v1/me", "sourceIp": "1.1.1.1"},
                    "requestId": "r",
                    "stage": "$default",
                },
                "isBase64Encoded": False,
            },
            None,
        )["statusCode"]
        == 401
    )


def test_expired_cursor_returns_410(deps: Deps) -> None:
    from tasklane.workmgmt.boards import encode_cursor

    status, body = call(
        deps, "POST", "/api/v1/boards/10/changes", {"since_xmin": encode_cursor(1, 0, 1_700_000_000)}
    )
    assert status == 410 and body["error"]["code"] == "gone"


def test_publish_failure_after_commit_still_returns_the_write(deps: Deps) -> None:  # M0B-11
    class Down:
        def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
            raise ConnectionError("EventBridge unavailable")

    deps.publisher = Down()
    status, body = call(deps, "PATCH", "/api/v1/items/1003/values", {"values": {"note": "x"}})
    assert (
        status == 200 and body["version"] == 2
    )  # the outbox row stays unpublished; the sweeper republishes it
