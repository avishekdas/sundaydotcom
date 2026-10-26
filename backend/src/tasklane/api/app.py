"""`api` λ (ADR-003): thin adapters over domain services (arch 04 §4.4). Skeleton routes for M0b."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from functools import cache
from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response, content_types

from tasklane.collab.realtime import DynamoRegistry, Registry
from tasklane.platform.clock import Clock, SystemClock
from tasklane.platform.db import Db
from tasklane.platform.outbox import EventBridgePublisher, Publisher, publish_after_commit
from tasklane.workmgmt import boards

STATUS = {
    "validation_error": 400,
    "unauthenticated": 401,
    "forbidden": 403,
    "not_found": 404,
    "version_conflict": 409,
    "gone": 410,
    "rate_limited": 429,
    "stale_epoch": 409,
}


@dataclass
class Deps:
    db: Db
    publisher: Publisher
    registry: Registry
    clock: Clock
    ws_url: str
    bus_name: str


class ApiError(Exception):
    def __init__(self, code: str, message: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.fields = code, message, fields


app = APIGatewayHttpResolver()
_deps: Deps | None = None


def _error(code: str, message: str, fields: dict[str, str] | None = None) -> Response[str]:
    err: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": app.current_event.request_context.request_id,
    }
    if fields:
        err["fields"] = fields
    return Response(
        status_code=STATUS.get(code, 500),
        content_type=content_types.APPLICATION_JSON,
        body=json.dumps({"error": err}),
    )


@app.exception_handler(ApiError)  # type: ignore[untyped-decorator]
def _api_error(e: ApiError) -> Response[str]:
    return _error(e.code, e.message, e.fields)


@app.exception_handler(boards.ValidationFailed)  # type: ignore[untyped-decorator]
def _validation(e: boards.ValidationFailed) -> Response[str]:
    return _error("validation_error", "Invalid request", e.fields)


@app.exception_handler(boards.CursorExpired)  # type: ignore[untyped-decorator]
def _gone(_e: boards.CursorExpired) -> Response[str]:
    return _error("gone", "Cursor expired; reload the board")


@app.not_found
def _not_found(_e: Exception) -> Response[str]:
    return _error("not_found", "Not found")


def deps() -> Deps:
    assert _deps is not None
    return _deps


def _body() -> dict[str, Any]:
    raw = app.current_event.body
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except ValueError:
        raise ApiError("validation_error", "Body must be JSON") from None
    if not isinstance(body, dict):
        raise ApiError("validation_error", "Body must be a JSON object")
    return body


def _int(v: str) -> int:
    if not v.isdigit():
        raise ApiError("not_found", "Not found")
    return int(v)


def current_user() -> dict[str, Any]:
    """Identity-only JWT (F7.7): resolve the user and the permission epoch from the DB."""
    authorizer = app.current_event.raw_event.get("requestContext", {}).get("authorizer") or {}
    sub = (authorizer.get("jwt") or {}).get("claims", {}).get("sub")
    if not sub:
        raise ApiError("unauthenticated", "Sign in required")
    try:
        uuid.UUID(sub)
    except ValueError:
        raise ApiError("unauthenticated", "Sign in required") from None
    rows = deps().db.query(
        """select u.id::text as id, u.name, u.email::text as email, u.role, (select perm_epoch from tl.account) as epoch
           from tl.users u where u.cognito_sub = :sub::uuid and u.status = 'active'""",
        {"sub": sub},
    )
    if not rows:
        raise ApiError("unauthenticated", "Sign in required")
    return rows[0]


@app.get("/api/v1/me")
def me() -> dict[str, Any]:
    u = current_user()
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"]}


@app.get("/api/v1/boards/<board_id>/schema")
def schema(board_id: str) -> dict[str, Any]:
    current_user()
    doc = boards.get_schema(deps().db, _int(board_id))
    if doc is None:
        raise ApiError("not_found", "Not found")
    return doc


@app.post("/api/v1/boards/<board_id>/query")
def query(board_id: str) -> dict[str, Any]:
    current_user()
    return boards.query_board(deps().db, _int(board_id))


@app.post("/api/v1/boards/<board_id>/items:fetch")
def items_fetch(board_id: str) -> dict[str, Any]:
    current_user()
    ids = _body().get("ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ApiError("validation_error", "ids must be a list of strings", {"ids": "list of strings"})
    return {"items": boards.fetch_items(deps().db, _int(board_id), ids)}


@app.patch("/api/v1/items/<item_id>/values")
def patch_values(item_id: str) -> dict[str, Any]:
    u = current_user()
    body = _body()
    values = body.get("values")
    if not isinstance(values, dict) or not values:
        raise ApiError("validation_error", "values must be a non-empty object", {"values": "required"})
    mid = body.get("mutation_id") or str(uuid.uuid4())
    actor = boards.Actor(user_id=int(u["id"]), cached_epoch=int(u["epoch"]))
    res = boards.set_values(deps().db, actor, _int(item_id), values, mutation_id=str(mid))
    if res.failure == "stale_epoch":  # re-authorize and retry once (FR-9)
        fresh = current_user()
        res = boards.set_values(
            deps().db,
            boards.Actor(int(fresh["id"]), int(fresh["epoch"])),
            _int(item_id),
            values,
            mutation_id=str(mid),
        )
    if res.failure:
        raise ApiError("not_found" if res.failure == "not_found" else "forbidden", "Cannot update this item")
    try:  # the write is committed; a failed publish is left to the sweeper (outbox), never a 500 (M0B-11)
        publish_after_commit(deps().publisher, res.events, bus_name=deps().bus_name, source="tasklane")
    except Exception as e:
        print(json.dumps({"metric": "outbox.publish_error", "error": type(e).__name__}))
    return {"id": item_id, "version": res.version, "values": res.values, "computed_pending": True}


@app.post("/api/v1/boards/<board_id>/changes")
def board_changes(board_id: str) -> dict[str, Any]:
    current_user()
    since = _body().get("since_xmin")
    if since is not None and not isinstance(since, str):
        raise ApiError("validation_error", "since_xmin must be a string", {"since_xmin": "string"})
    return boards.changes(deps().db, _int(board_id), since_xmin=since)


@app.post("/api/v1/realtime/ticket")
def realtime_ticket() -> dict[str, Any]:
    u = current_user()
    return {"ticket": deps().registry.issue_ticket(int(u["id"])), "url": deps().ws_url}


def handle(event: dict[str, Any], d: Deps) -> dict[str, Any]:
    global _deps
    _deps = d
    return app.resolve(event, None)  # type: ignore[arg-type]


@cache
def _env_deps() -> Deps:
    from tasklane.platform.aws_env import boto, db_from_env

    clock = SystemClock()
    return Deps(
        db=db_from_env(),
        publisher=EventBridgePublisher(boto("events")),
        registry=DynamoRegistry(boto("dynamodb"), os.environ["REALTIME_TABLE"], clock),
        clock=clock,
        ws_url=os.environ["WS_URL"],
        bus_name=os.environ["EVENT_BUS_NAME"],
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if os.environ.get("TL_FAULT_INJECTION") == "1" and os.environ.get("STAGE") != "prod":
        raise RuntimeError("fault injection: canary rollback rehearsal (ops/rehearse_canary_rollback.md)")
    return handle(event, _env_deps())
