"""Tier A north star — M1 steps (contracts/north_star.yaml).

Step 7 is generated over the **current route inventory** (plan §1.1, TP-13): every route is either declared a read
route here (a Viewer must succeed) or treated as a write (a Viewer must get 403). A new route is therefore a write
until someone declares it a read, so the check grows with the API automatically. Authorization runs before body
validation, so unknown writes are probed with an empty body.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from tasklane.api.app import Deps, handle, route_inventory
from tasklane.collab.realtime import InMemoryRegistry
from tasklane.identity.auth_backend import FakeAuthBackend
from tasklane.identity.auth_proxy import AuthProxy
from tasklane.platform.clock import FakeClock
from tasklane.platform.counters import InMemoryCounters
from tasklane.platform.db import StrictDataApiFake

pytestmark = [pytest.mark.integration]

VIEWER_SUB = "00000000-0000-0000-0000-000000000043"
PATH_PARAMS = {"board_id": "10", "item_id": "1001", "workspace_id": "1", "user_id": "43"}

# Routes a Viewer may call (K1: viewers read everything they can see).
READ_ROUTES = {
    ("GET", "/api/v1/me"),
    ("GET", "/api/v1/boards/<board_id>/schema"),
    ("POST", "/api/v1/boards/<board_id>/query"),
    ("POST", "/api/v1/boards/<board_id>/items:fetch"),
    ("POST", "/api/v1/boards/<board_id>/changes"),
    ("POST", "/api/v1/realtime/ticket"),
    ("POST", "/api/v1/me/sign-out-everywhere"),  # self-service on the caller's own sessions (D-052)
    ("GET", "/api/v1/nav"),
    ("GET", "/api/v1/workspaces/<workspace_id>"),
    ("GET", "/api/v1/account"),
    ("GET", "/api/v1/boards/<board_id>"),
    ("PATCH", "/api/v1/me"),  # own profile (A16)
}
# Unauthenticated auth-proxy routes (07 §7.1) sit outside the JWT authorizer and outside this check.
PUBLIC_PREFIX = "/api/auth/"
# Valid bodies, so a write is refused for the right reason (not a 400) — unknown writes get {}.
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/api/v1/boards/<board_id>/items:fetch"): {"ids": ["1001"]},
    ("PATCH", "/api/v1/me"): {"title": "Viewer"},
    ("PATCH", "/api/v1/items/<item_id>/values"): {"values": {"note": "viewer was here"}},
    ("POST", "/api/v1/boards/<board_id>/columns"): {"title": "Viewer column"},
    ("POST", "/api/v1/workspaces"): {"name": "Viewer space", "kind": "open"},
    ("PATCH", "/api/v1/workspaces/<workspace_id>"): {"name": "Renamed"},
    ("PUT", "/api/v1/workspaces/<workspace_id>/members/<user_id>"): {"role": "member"},
    ("POST", "/api/v1/boards/<board_id>/move"): {"before_id": None},
    ("POST", "/api/v1/users"): {"email": "viewer-invite@example.com", "name": "V", "role": "member"},
    ("PATCH", "/api/v1/users/<user_id>"): {"role": "member"},
    ("PATCH", "/api/v1/account/settings"): {"name": "Viewer Inc"},
    ("PATCH", "/api/v1/boards/<board_id>"): {"kind": "private"},
    ("PUT", "/api/v1/boards/<board_id>/members/<user_id>"): {"role": "member"},
}


def _call(deps: Deps, method: str, template: str, sub: str) -> int:
    path = re.sub(r"<(\w+)>", lambda m: PATH_PARAMS[m.group(1)], template)
    body = BODIES.get((method, template), {})
    ev = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "http": {"method": method, "path": path, "sourceIp": "1.1.1.1"},
            "requestId": "r",
            "stage": "$default",
            "authorizer": {"jwt": {"claims": {"sub": sub}}},
        },
        "body": json.dumps(body) if method != "GET" else None,
        "isBase64Encoded": False,
    }
    return int(handle(ev, deps)["statusCode"])


@pytest.fixture
def viewer_deps(board_db: str) -> Deps:
    with psycopg.connect(board_db, autocommit=True) as c:
        c.execute(
            "insert into tl.users (id, email, name, role, status, cognito_sub) values "
            "(43, 'v@example.com', 'Vic', 'viewer', 'active', %s)",
            (VIEWER_SUB,),
        )
    clock = FakeClock(datetime(2026, 10, 26, 12, tzinfo=UTC))

    class _NoPublish:
        def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
            return []

    return Deps(
        db=StrictDataApiFake(board_db),
        publisher=_NoPublish(),
        registry=InMemoryRegistry(clock),
        clock=clock,
        ws_url="/ws",
        bus_name="t",
        auth=AuthProxy(FakeAuthBackend(clock), InMemoryCounters(clock), clock),
    )


def test_read_routes_are_registered() -> None:
    assert set(route_inventory()) >= READ_ROUTES, "a declared read route no longer exists"


def test_every_route_is_versioned_api_or_auth_proxy() -> None:
    assert all(p.startswith(("/api/v1/", PUBLIC_PREFIX)) for _, p in route_inventory())


def _authenticated_routes() -> list[tuple[str, str]]:
    return [(m, p) for m, p in route_inventory() if not p.startswith(PUBLIC_PREFIX)]


@pytest.mark.north_star("7.viewer_read_only")
def test_viewer_reads_every_read_route_and_is_refused_on_every_other(viewer_deps: Deps) -> None:
    got = {(m, p): _call(viewer_deps, m, p, VIEWER_SUB) for m, p in _authenticated_routes()}
    reads_failing = {r: s for r, s in got.items() if r in READ_ROUTES and s != 200}
    writes_allowed = {r: s for r, s in got.items() if r not in READ_ROUTES and s != 403}
    assert not reads_failing, f"viewer could not read: {reads_failing}"
    assert not writes_allowed, f"viewer was not refused (expected 403): {writes_allowed}"
