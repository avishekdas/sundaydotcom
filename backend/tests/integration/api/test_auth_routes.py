"""Auth proxy HTTP surface (`/api/auth/*`, arch 07 §7.1, D-043…D-052): routes outside the JWT authorizer, refresh
token in an HttpOnly cookie scoped to `/api/auth`, viewer IP from `CloudFront-Viewer-Address`, and the CloudFront
origin secret header (`x-tl-origin`, 07 §7.4, D-050) required on every route."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from tasklane.api.app import Deps, handle
from tasklane.collab.realtime import InMemoryRegistry
from tasklane.identity.auth_backend import FakeAuthBackend
from tasklane.identity.auth_proxy import AuthProxy
from tasklane.platform.clock import FakeClock
from tasklane.platform.counters import InMemoryCounters
from tasklane.platform.db import StrictDataApiFake

pytestmark = pytest.mark.integration
ORIGIN = "origin-secret-for-tests"
GOOD = "Correct-Horse-Battery-9"
ADA_SUB = "00000000-0000-0000-0000-000000000042"


class _NoPublish:
    def put_events(self, entries: list[dict[str, Any]]) -> list[int]:
        return []


@pytest.fixture
def deps(board_db: str) -> Deps:
    clock = FakeClock(datetime(2026, 10, 26, 12, tzinfo=UTC))
    backend = FakeAuthBackend(clock)
    backend.add_user("a@example.com", GOOD)
    return Deps(
        db=StrictDataApiFake(board_db),
        publisher=_NoPublish(),
        registry=InMemoryRegistry(clock),
        clock=clock,
        ws_url="/ws",
        bus_name="t",
        auth=AuthProxy(backend, InMemoryCounters(clock), clock, sleep=lambda s: clock.advance(seconds=s)),
        origin_secret=ORIGIN,
    )


def call(
    deps: Deps,
    method: str,
    path: str,
    body: Any = None,
    *,
    ip: str | None = "203.0.113.1:443",
    origin: str | None = ORIGIN,
    cookies: list[str] | None = None,
    sub: str | None = None,
) -> dict[str, Any]:
    headers = {"content-type": "application/json"}
    if ip:
        headers["cloudfront-viewer-address"] = ip
    if origin:
        headers["x-tl-origin"] = origin
    ev: dict[str, Any] = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": headers,
        "cookies": cookies or [],
        "requestContext": {
            "http": {"method": method, "path": path, "sourceIp": "10.0.0.1"},
            "requestId": "r",
            "stage": "$default",
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }
    if sub:
        ev["requestContext"]["authorizer"] = {"jwt": {"claims": {"sub": sub}}}
    res = handle(ev, deps)
    res["json"] = json.loads(res["body"]) if res.get("body") else None
    return res


def _rt_cookie(res: dict[str, Any]) -> str:
    c = next(c for c in res.get("cookies", []) if c.startswith("tl_rt="))
    return c.split(";", 1)[0]


def test_sign_in_returns_access_token_and_sets_refresh_cookie(deps: Deps) -> None:
    res = call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com", "password": GOOD})
    assert res["statusCode"] == 200
    assert res["json"]["access_token"] and res["json"]["expires_in"] > 0
    assert "refresh_token" not in res["json"]  # only in the HttpOnly cookie
    cookie = next(c for c in res["cookies"] if c.startswith("tl_rt="))
    for attr in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/api/auth", "Max-Age=2592000"):
        assert attr in cookie  # D-048: 30 days


@pytest.mark.ac("AC-K7-2")
def test_ac_k7_2_over_http(deps: Deps) -> None:
    for _ in range(5):
        r = call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com", "password": "bad-bad-bad-1"})
        assert r["statusCode"] == 401
    sixth = call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com", "password": GOOD})
    assert sixth["statusCode"] == 429 and int(sixth["headers"]["Retry-After"]) > 0
    other = call(
        deps,
        "POST",
        "/api/auth/sign-in",
        {"email": "a@example.com", "password": GOOD},
        ip="[2001:db8:9:9::1]:443",
    )
    assert other["statusCode"] == 200


def test_errors_are_generic(deps: Deps) -> None:
    known = call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com", "password": "bad-bad-bad-1"})
    unknown = call(
        deps, "POST", "/api/auth/sign-in", {"email": "zz@example.com", "password": "bad-bad-bad-1"}
    )
    assert known["statusCode"] == unknown["statusCode"] == 401
    assert known["json"]["error"]["message"] == unknown["json"]["error"]["message"]


def test_sign_in_validates_body(deps: Deps) -> None:
    assert call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com"})["statusCode"] == 400


def test_missing_viewer_address_is_refused(deps: Deps) -> None:
    res = call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com", "password": GOOD}, ip=None)
    assert res["statusCode"] == 403


@pytest.mark.parametrize("origin", [None, "wrong"])
def test_origin_secret_required_on_every_route(deps: Deps, origin: str | None) -> None:
    assert (
        call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com", "password": GOOD}, origin=origin)[
            "statusCode"
        ]
        == 403
    )
    assert call(deps, "GET", "/api/v1/me", origin=origin, sub=ADA_SUB)["statusCode"] == 403
    assert call(deps, "GET", "/api/v1/me", sub=ADA_SUB)["statusCode"] == 200


def test_refresh_and_sign_out(deps: Deps) -> None:
    rt = _rt_cookie(call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com", "password": GOOD}))
    assert call(deps, "POST", "/api/auth/refresh")["statusCode"] == 401  # no cookie
    ok = call(deps, "POST", "/api/auth/refresh", cookies=[rt])
    assert ok["statusCode"] == 200 and ok["json"]["access_token"]
    out = call(deps, "POST", "/api/auth/sign-out", cookies=[rt])
    assert out["statusCode"] == 204
    assert any(c.startswith("tl_rt=;") and "Max-Age=0" in c for c in out["cookies"])
    assert call(deps, "POST", "/api/auth/refresh", cookies=[rt])["statusCode"] == 401


def test_sign_out_everywhere_needs_a_session(deps: Deps) -> None:
    rt = _rt_cookie(call(deps, "POST", "/api/auth/sign-in", {"email": "a@example.com", "password": GOOD}))
    assert call(deps, "POST", "/api/v1/me/sign-out-everywhere")["statusCode"] == 401
    assert call(deps, "POST", "/api/v1/me/sign-out-everywhere", sub=ADA_SUB)["statusCode"] == 200
    assert call(deps, "POST", "/api/auth/refresh", cookies=[rt])["statusCode"] == 401
