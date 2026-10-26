"""Local dev server (`make dev`, DL-9): the real `api` handler behind a Starlette shim.

HTTP → API Gateway v2 events (dev identity: ``Authorization: Bearer dev-<cognito sub>``), synchronous InProcessBus
with the real fan-out, and a local WebSocket at /ws. Never deployed: nothing under ``tasklane.api`` or
``tasklane.workers`` imports this package (import-linter layers).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from tasklane.api.app import Deps, handle
from tasklane.collab.realtime import InMemoryRegistry, fan_out
from tasklane.platform.bus import Event, InProcessBus
from tasklane.platform.clock import SystemClock
from tasklane.platform.db import PsycopgDb, StrictDataApiFake
from tasklane.platform.migrations import apply_migrations
from tasklane.platform.sql_script import split_statements
from tasklane.workers.ws_handlers import handle as ws_handle

DEV_SUB = "00000000-0000-4000-8000-00000000d001"
REPO = Path(__file__).resolve().parents[4]
_TOKEN = re.compile(r"^Bearer dev-([0-9a-f-]{36})$")


class _BusPublisher:
    def __init__(self, bus: InProcessBus) -> None:
        self.bus = bus

    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        for e in entries:
            d = json.loads(e["Detail"])
            self.bus.publish(Event(type=d["type"], event_id=d["event_id"], payload=d))
        self.bus.drain()
        return []


class _LocalGateway:
    def __init__(self) -> None:
        self.sockets: dict[str, WebSocket] = {}

    def send(self, connection_id: str, message: dict[str, Any]) -> bool:
        ws = self.sockets.get(connection_id)
        if ws is None:
            return False
        asyncio.get_event_loop().create_task(ws.send_json(message))
        return True


def _seed(db: PsycopgDb) -> None:
    sql = (REPO / "ops" / "seed" / "m0b_demo.sql").read_text()
    for stmt in split_statements(sql):
        stmt = re.sub(r"--[^\n]*\n", "", stmt).strip()
        db.execute(stmt, {"sub": DEV_SUB} if ":sub" in stmt else None)


def create_app(*, pg_uri: str | None = None, seed: bool = True) -> Starlette:
    if pg_uri is None:
        import embedded_postgres

        pg_uri = embedded_postgres.get_server(tempfile.mkdtemp(prefix="tl-dev-")).get_uri()  # type: ignore[attr-defined]
    apply_migrations(pg_uri, REPO / "backend" / "migrations")
    db = StrictDataApiFake(pg_uri)
    if seed:
        _seed(db)
    clock = SystemClock()
    bus = InProcessBus()
    registry = InMemoryRegistry(clock)
    gateway = _LocalGateway()

    def push(e: Event) -> None:
        fan_out(registry, gateway, e.payload)

    bus.subscribe("item.*", push)
    deps = Deps(
        db=db, publisher=_BusPublisher(bus), registry=registry, clock=clock, ws_url="/ws", bus_name="local"
    )

    async def config(_r: Request) -> Response:
        return JSONResponse(
            {
                "stage": "local",
                "apiBase": "/api/v1",
                "authBase": "/api/auth",
                "wsPath": "/ws",
                "auth": "dev",
                "devToken": f"dev-{DEV_SUB}",
            }
        )

    async def api(r: Request) -> Response:
        body = (await r.body()).decode() or None
        ctx: dict[str, Any] = {
            "http": {"method": r.method, "path": r.url.path, "sourceIp": "127.0.0.1"},
            "requestId": "local",
            "stage": "$default",
        }
        m = _TOKEN.match(r.headers.get("authorization", ""))
        if m:
            ctx["authorizer"] = {"jwt": {"claims": {"sub": m.group(1)}}}
        else:  # the JWT authorizer rejects before the λ runs
            return JSONResponse({"message": "Unauthorized"}, status_code=401)
        event = {
            "version": "2.0",
            "routeKey": f"{r.method} {r.url.path}",
            "rawPath": r.url.path,
            "rawQueryString": r.url.query,
            "headers": dict(r.headers),
            "requestContext": ctx,
            "body": body,
            "isBase64Encoded": False,
        }
        res = handle(event, deps)
        return Response(
            res.get("body") or "",
            status_code=res["statusCode"],
            headers={"content-type": res.get("headers", {}).get("Content-Type", "application/json")},
        )

    async def ws(socket: WebSocket) -> None:
        conn = f"local-{id(socket)}"
        rc = ws_handle(
            {
                "requestContext": {"routeKey": "$connect", "connectionId": conn},
                "queryStringParameters": dict(socket.query_params),
            },
            registry,
        )
        if rc["statusCode"] != 200:
            await socket.close(code=4401)
            return
        await socket.accept()
        gateway.sockets[conn] = socket
        try:
            while True:
                text = await socket.receive_text()
                out = ws_handle(
                    {"requestContext": {"routeKey": "$default", "connectionId": conn}, "body": text}, registry
                )
                if out.get("body"):
                    await socket.send_text(out["body"])
        except WebSocketDisconnect:
            pass
        finally:
            gateway.sockets.pop(conn, None)
            ws_handle({"requestContext": {"routeKey": "$disconnect", "connectionId": conn}}, registry)

    return Starlette(
        routes=[
            Route("/config.json", config),
            Route("/api/v1/{path:path}", api, methods=["GET", "POST", "PATCH", "PUT", "DELETE"]),
            WebSocketRoute("/ws", ws),
        ]
    )


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(pg_uri=os.environ.get("TL_DEV_PG_URI")), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
