"""Shared M1 test world: users per role and a JWT-authorized API caller (identity-only claims, F7.7)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import psycopg

from tasklane.api.app import Deps, handle
from tasklane.collab.realtime import InMemoryRegistry
from tasklane.platform.clock import FakeClock
from tasklane.platform.db import StrictDataApiFake

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
SUBS = {
    "ada": "00000000-0000-0000-0000-000000000042",  # admin (board_db)
    "vic": "00000000-0000-0000-0000-000000000043",  # viewer
    "mia": "00000000-0000-0000-0000-000000000044",  # member
    "raj": "00000000-0000-0000-0000-000000000045",  # member
}
IDS = {"ada": 42, "vic": 43, "mia": 44, "raj": 45}


class _NoPublish:
    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        return []


def add_users(uri: str) -> None:
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute(
            "insert into tl.users (id, email, name, role, status, cognito_sub) values "
            "(43, 'v@example.com', 'Vic', 'viewer', 'active', %s), (44, 'm@example.com', 'Mia', 'member', 'active', %s),"
            " (45, 'r@example.com', 'Raj', 'member', 'active', %s)",
            (SUBS["vic"], SUBS["mia"], SUBS["raj"]),
        )


def make_deps(uri: str) -> Deps:
    clock = FakeClock(NOW)
    return Deps(
        db=StrictDataApiFake(uri),
        publisher=_NoPublish(),
        registry=InMemoryRegistry(clock),
        clock=clock,
        ws_url="/ws",
        bus_name="t",
    )


def call(deps: Deps, who: str, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    claims = {"sub": SUBS[who], "iat": str(int(NOW.timestamp()))}
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
            "authorizer": {"jwt": {"claims": claims}},
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }
    res = handle(ev, deps)
    return res["statusCode"], json.loads(res["body"]) if res.get("body") else None
