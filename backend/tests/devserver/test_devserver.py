"""`make dev` local stack (DL-9): devserver shim → real api handler, InProcessBus, local WebSocket."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from tasklane.devserver.app import DEV_SUB, create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def client(fresh_db: str) -> TestClient:
    return TestClient(create_app(pg_uri=fresh_db, seed=True))


def test_config_announces_dev_auth(client: TestClient) -> None:
    cfg = client.get("/config.json").json()
    assert cfg["stage"] == "local" and cfg["auth"] == "dev" and cfg["devToken"] == f"dev-{DEV_SUB}"


def test_api_requires_the_dev_token(client: TestClient) -> None:
    assert client.get("/api/v1/me").status_code == 401
    r = client.get("/api/v1/me", headers={"authorization": f"Bearer dev-{DEV_SUB}"})
    assert r.status_code == 200 and r.json()["name"] == "Test User A"


def test_websocket_receives_pushes_after_a_write(client: TestClient) -> None:
    h = {"authorization": f"Bearer dev-{DEV_SUB}"}
    ticket = client.post("/api/v1/realtime/ticket", json={}, headers=h).json()
    assert ticket["url"] == "/ws"
    with client.websocket_connect(f"/ws?ticket={ticket['ticket']}") as ws:
        ws.send_json({"action": "subscribe", "board_id": "10"})
        assert ws.receive_json() == {"type": "subscribed", "board_id": "10"}
        r = client.patch("/api/v1/items/1001/values", json={"values": {"note": "local"}}, headers=h)
        assert r.status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "item.values_changed" and msg["item_id"] == "1001" and msg["values"] == {"note": "local"}


def test_websocket_rejects_a_bad_ticket(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws?ticket=nope") as ws:
        ws.receive_json()
