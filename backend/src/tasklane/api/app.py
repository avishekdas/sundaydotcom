"""`api` λ (ADR-003): thin adapters over domain services (arch 04 §4.4). Skeleton routes for M0b."""

from __future__ import annotations

import hmac
import json
import os
import uuid
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response, content_types
from aws_lambda_powertools.shared.cookies import Cookie, SameSite

from tasklane.collab.realtime import DynamoRegistry, Registry
from tasklane.identity.auth_proxy import AuthProxy, AuthRefused
from tasklane.identity.authz import Cap
from tasklane.identity.snapshot import PermissionSnapshot, SnapshotCache
from tasklane.identity.viewer_ip import BadViewerAddress, viewer_ip_key
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
    "conflict": 409,
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
    auth: AuthProxy | None = None  # auth proxy (07 §7.1); None where sign-in is not served (devserver)
    origin_secret: str | None = None  # CloudFront `x-tl-origin` (07 §7.4, D-050); None disables the check
    snapshots: SnapshotCache = field(default_factory=SnapshotCache)  # per Lambda instance, ≤ 30 s (07 §7.2)


class ApiError(Exception):
    def __init__(
        self, code: str, message: str, fields: dict[str, str] | None = None, retry_after_s: int | None = None
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.fields, self.retry_after_s = code, message, fields, retry_after_s


app = APIGatewayHttpResolver()
_deps: Deps | None = None


def _error(
    code: str, message: str, fields: dict[str, str] | None = None, retry_after_s: int | None = None
) -> Response[str]:
    err: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": app.current_event.request_context.request_id,
    }
    if fields:
        err["fields"] = fields
    headers: dict[str, str] = {}
    if retry_after_s:
        err["retry_after_s"] = retry_after_s
        headers["Retry-After"] = str(retry_after_s)
    return Response(
        status_code=STATUS.get(code, 500),
        content_type=content_types.APPLICATION_JSON,
        body=json.dumps({"error": err}),
        headers=headers,
    )


@app.exception_handler(ApiError)  # type: ignore[untyped-decorator]
def _api_error(e: ApiError) -> Response[str]:
    return _error(e.code, e.message, e.fields, e.retry_after_s)


@app.exception_handler(AuthRefused)  # type: ignore[untyped-decorator]
def _auth_refused(e: AuthRefused) -> Response[str]:
    return _error(e.code, e.message, e.fields, e.retry_after_s)


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


def reset_permission_cache() -> None:
    """Forget every cached PermissionSnapshot of the current instance."""
    if _deps is not None:
        _deps.snapshots.clear()


def _claims() -> dict[str, Any]:
    authorizer = app.current_event.raw_event.get("requestContext", {}).get("authorizer") or {}
    return dict((authorizer.get("jwt") or {}).get("claims", {}))


def snapshot(*, fresh: bool = False) -> PermissionSnapshot:
    """Identity-only JWT (F7.7): the user, role and permissions come from the DB, never from token claims."""
    claims = _claims()
    sub = claims.get("sub")
    try:
        uuid.UUID(str(sub))
    except ValueError:
        raise ApiError("unauthenticated", "Sign in required") from None
    snap = deps().snapshots.get(deps().db, deps().clock, str(sub), fresh=fresh)
    if snap is None:
        raise ApiError("unauthenticated", "Sign in required")
    try:
        iat = int(claims.get("iat", 0))
    except (TypeError, ValueError):
        iat = 0
    if iat < snap.tokens_valid_after:  # revoked by reset / sign-out-everywhere / deactivation (AR-9)
        raise ApiError("unauthenticated", "Session expired; sign in again")
    return snap


def current_user() -> dict[str, Any]:
    s = snapshot()
    return {"id": str(s.user_id), "name": s.name, "email": s.email, "role": s.role, "epoch": s.epoch}


def _board(board_id: str, cap: Cap, snap: PermissionSnapshot | None = None) -> tuple[int, PermissionSnapshot]:
    """Authorize before anything else (bodies are validated afterwards): invisible → 404, missing cap → 403."""
    b = _int(board_id)
    s = snap or snapshot()
    caps = s.caps(b)
    if caps is None:
        raise ApiError("not_found", "Not found")
    if cap not in caps:
        raise ApiError("forbidden", "You do not have permission to do this")
    return b, s


@app.get("/api/v1/me")
def me() -> dict[str, Any]:
    s = snapshot()
    return {
        "id": str(s.user_id),
        "name": s.name,
        "email": s.email,
        "role": s.role,
        "capabilities": sorted(c.value for c in s.account_caps()),
    }


@app.get("/api/v1/boards/<board_id>/schema")
def schema(board_id: str) -> dict[str, Any]:
    b, s = _board(board_id, Cap.READ)
    doc = boards.get_schema(deps().db, b)
    if doc is None:
        raise ApiError("not_found", "Not found")
    caps = s.caps(b) or frozenset()
    return {**doc, "capabilities": sorted(c.value for c in caps)}  # the UI hides what the caller cannot do


@app.post("/api/v1/boards/<board_id>/query")
def query(board_id: str) -> dict[str, Any]:
    b, _ = _board(board_id, Cap.READ)
    return boards.query_board(deps().db, b)


@app.post("/api/v1/boards/<board_id>/items:fetch")
def items_fetch(board_id: str) -> dict[str, Any]:
    b, _ = _board(board_id, Cap.READ)
    ids = _body().get("ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ApiError("validation_error", "ids must be a list of strings", {"ids": "list of strings"})
    return {"items": boards.fetch_items(deps().db, b, ids)}


@app.patch("/api/v1/items/<item_id>/values")
def patch_values(item_id: str) -> dict[str, Any]:
    item = _int(item_id)
    board = boards.board_of_item(deps().db, item)
    if board is None:
        raise ApiError("not_found", "Not found")
    _, s = _board(str(board), Cap.EDIT_VALUES)
    body = _body()
    values = body.get("values")
    if not isinstance(values, dict) or not values:
        raise ApiError("validation_error", "values must be a non-empty object", {"values": "required"})
    mid = str(body.get("mutation_id") or uuid.uuid4())
    res = boards.set_values(deps().db, boards.Actor(s.user_id, s.epoch), item, values, mutation_id=mid)
    if (
        res.failure == "stale_epoch"
    ):  # permissions changed since the snapshot: re-authorize and retry once (FR-9)
        _, s = _board(str(board), Cap.EDIT_VALUES, snapshot(fresh=True))
        res = boards.set_values(deps().db, boards.Actor(s.user_id, s.epoch), item, values, mutation_id=mid)
    if res.failure:
        raise ApiError("not_found" if res.failure == "not_found" else "forbidden", "Cannot update this item")
    try:  # the write is committed; a failed publish is left to the sweeper (outbox), never a 500 (M0B-11)
        publish_after_commit(deps().publisher, res.events, bus_name=deps().bus_name, source="tasklane")
    except Exception as e:
        print(json.dumps({"metric": "outbox.publish_error", "error": type(e).__name__}))
    return {"id": item_id, "version": res.version, "values": res.values, "computed_pending": True}


@app.post("/api/v1/boards/<board_id>/changes")
def board_changes(board_id: str) -> dict[str, Any]:
    b, _ = _board(board_id, Cap.READ)
    since = _body().get("since_xmin")
    if since is not None and not isinstance(since, str):
        raise ApiError("validation_error", "since_xmin must be a string", {"since_xmin": "string"})
    return boards.changes(deps().db, b, since_xmin=since)


@app.post("/api/v1/boards/<board_id>/columns")
def create_column(board_id: str) -> Response[str]:
    b, _ = _board(board_id, Cap.EDIT_STRUCTURE)
    title = _body().get("title")
    if not isinstance(title, str):
        raise ApiError("validation_error", "Invalid request", {"title": "Required"})
    try:
        col = boards.create_text_column(deps().db, b, title)
    except boards.TitleTaken:
        raise ApiError(
            "conflict", "A column with this title already exists", {"title": "Already used"}
        ) from None
    return Response(status_code=201, content_type=content_types.APPLICATION_JSON, body=json.dumps(col))


@app.post("/api/v1/realtime/ticket")
def realtime_ticket() -> dict[str, Any]:
    u = current_user()
    return {"ticket": deps().registry.issue_ticket(int(u["id"])), "url": deps().ws_url}


# --- auth proxy (07 §7.1): outside the JWT authorizer; refresh token only in an HttpOnly cookie -----------------
REFRESH_COOKIE = "tl_rt"
REFRESH_MAX_AGE_S = 30 * 24 * 3600  # D-048


def _auth() -> AuthProxy:
    a = deps().auth
    if a is None:
        raise ApiError("not_found", "Not found")
    return a


def _viewer_ip() -> str:
    try:
        return viewer_ip_key(app.current_event.headers.get("cloudfront-viewer-address"))
    except BadViewerAddress:
        raise ApiError("forbidden", "Forbidden") from None


def _refresh_cookie(value: str, max_age: int) -> Cookie:
    return Cookie(
        name=REFRESH_COOKIE,
        value=value,
        path="/api/auth",
        secure=True,
        http_only=True,
        max_age=max_age,
        same_site=SameSite.STRICT_MODE,
    )


def _cookie_value() -> str | None:
    for c in app.current_event.cookies or []:
        name, _, value = c.partition("=")
        if name.strip() == REFRESH_COOKIE and value:
            return value
    return None


@app.post("/api/auth/sign-in")
def auth_sign_in() -> Response[str]:
    body = _body()
    email, password = body.get("email"), body.get("password")
    fields = {
        k: "Required"
        for k, v in (("email", email), ("password", password))
        if not isinstance(v, str) or not v
    }
    if fields:
        raise ApiError("validation_error", "Email and password are required", fields)
    assert isinstance(email, str) and isinstance(password, str)
    t = _auth().sign_in(email, password, _viewer_ip())
    return Response(
        status_code=200,
        content_type=content_types.APPLICATION_JSON,
        body=json.dumps({"access_token": t.access_token, "expires_in": t.expires_in, "token_type": "Bearer"}),
        cookies=[_refresh_cookie(t.refresh_token or "", REFRESH_MAX_AGE_S)],
    )


@app.post("/api/auth/refresh")
def auth_refresh() -> dict[str, Any]:
    rt = _cookie_value()
    if rt is None:
        raise ApiError("unauthenticated", "Sign in required")
    t = _auth().refresh(rt, _viewer_ip())
    return {"access_token": t.access_token, "expires_in": t.expires_in, "token_type": "Bearer"}


@app.post("/api/auth/sign-out")
def auth_sign_out() -> Response[str]:
    rt = _cookie_value()
    if rt:
        _auth().sign_out(rt)
    return Response(status_code=204, body="", cookies=[_refresh_cookie("", 0)])


def _required(body: dict[str, Any], *names: str) -> list[str]:
    values = [body.get(n) for n in names]
    fields = {
        n: "Required" for n, v in zip(names, values, strict=True) if not isinstance(v, str) or not v.strip()
    }
    if fields:
        raise ApiError("validation_error", "Invalid request", fields)
    return [str(v) for v in values]


@app.post("/api/auth/forgot")
def auth_forgot() -> Response[str]:
    (email,) = _required(_body(), "email")
    _auth().forgot(email, _viewer_ip())
    return Response(status_code=202, body="")


def _bump_tokens_valid_after(email: str) -> None:
    # Access tokens issued before the reset are refused once PermissionSnapshot checks iat (07 §7.1, AR-9).
    deps().db.execute(
        "update tl.users set tokens_valid_after = date_trunc('second', now()), updated_at = now() where email = :email",
        {"email": email},
    )


@app.post("/api/auth/reset")
def auth_reset() -> Response[str]:
    email, code, new_password = _required(_body(), "email", "code", "new_password")
    _auth().reset(email, code.strip(), new_password, _viewer_ip(), on_reset=_bump_tokens_valid_after)
    return Response(status_code=204, body="", cookies=[_refresh_cookie("", 0)])


@app.post("/api/v1/me/sign-out-everywhere")
def sign_out_everywhere() -> dict[str, Any]:
    u = current_user()
    _auth().sign_out_everywhere(u["email"])
    return {"signed_out": True}


def route_inventory() -> list[tuple[str, str]]:
    """(METHOD, path template) for every registered route — drives generated tests (north-star step 7, AC-K3-4)."""
    routes = [*app._static_routes, *app._dynamic_routes]
    return sorted({(r.method.upper(), r.path) for r in routes})


def _origin_ok(event: dict[str, Any], secret: str) -> bool:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return hmac.compare_digest(str(headers.get("x-tl-origin", "")), secret)


def handle(event: dict[str, Any], d: Deps) -> dict[str, Any]:
    global _deps
    _deps = d
    if d.origin_secret and not _origin_ok(event, d.origin_secret):
        # Not through CloudFront (07 §7.4): the viewer-IP header could be forged, so nothing is served.
        request_id = (event.get("requestContext") or {}).get("requestId")
        body = {"error": {"code": "forbidden", "message": "Forbidden", "request_id": request_id}}
        return {"statusCode": 403, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body)}
    return app.resolve(event, None)  # type: ignore[arg-type]


@cache
def _env_deps() -> Deps:
    from tasklane.identity.auth_backend import CognitoAuth
    from tasklane.platform.aws_env import boto, db_from_env
    from tasklane.platform.counters import DynamoCounters

    clock = SystemClock()
    auth = AuthProxy(
        CognitoAuth(boto("cognito-idp"), os.environ["USER_POOL_ID"], os.environ["COGNITO_CLIENT_ID"]),
        DynamoCounters(boto("dynamodb"), os.environ["COUNTERS_TABLE"], clock),
        clock,
    )
    return Deps(
        db=db_from_env(),
        publisher=EventBridgePublisher(boto("events")),
        registry=DynamoRegistry(boto("dynamodb"), os.environ["REALTIME_TABLE"], clock),
        clock=clock,
        ws_url=os.environ["WS_URL"],
        bus_name=os.environ["EVENT_BUS_NAME"],
        auth=auth,
        origin_secret=os.environ["ORIGIN_SECRET"],
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if os.environ.get("TL_FAULT_INJECTION") == "1" and os.environ.get("STAGE") != "prod":
        raise RuntimeError("fault injection: canary rollback rehearsal (ops/rehearse_canary_rollback.md)")
    return handle(event, _env_deps())
