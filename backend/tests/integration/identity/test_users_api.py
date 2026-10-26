"""Users, invites, roles and deactivation (F1, F2, K1, K7.6; arch 07 §7.1 revocation; D-054).

One fake (FakeAuthBackend) plays Cognito for both the admin API (IdentityProvider) and the sign-in proxy, so an
invite can be accepted end to end. Invites carry a Cognito temporary password valid 7 days (F1.1).
"""

from __future__ import annotations

from typing import Any

import pytest

from tasklane.api.app import Deps
from tasklane.identity.auth_backend import FakeAuthBackend
from tasklane.identity.auth_proxy import AuthProxy
from tasklane.platform.counters import InMemoryCounters
from tests.integration.world import IDS, add_users, call, make_deps

pytestmark = pytest.mark.integration
NEW_PW = "Brand-New-Password-7"


@pytest.fixture
def deps(board_db: str) -> Deps:
    add_users(board_db)
    d = make_deps(board_db)
    cognito = FakeAuthBackend(d.clock)
    for email in ("a@example.com", "v@example.com", "m@example.com", "r@example.com"):
        cognito.add_user(email, "Existing-Password-1")
    d.idp = cognito
    d.auth = AuthProxy(cognito, InMemoryCounters(d.clock), d.clock, sleep=lambda s: None)
    return d


def cognito(deps: Deps) -> FakeAuthBackend:
    assert isinstance(deps.idp, FakeAuthBackend)
    return deps.idp


def public(deps: Deps, path: str, body: Any) -> tuple[int, Any, list[str]]:
    from tests.integration.api.test_auth_routes import call as raw_call

    res = raw_call(deps, "POST", path, body, origin=None)
    return res["statusCode"], res["json"], res.get("cookies", [])


def invite(deps: Deps, email: str = "new@example.com", role: str = "member") -> dict[str, Any]:
    status, user = call(
        deps, "ada", "POST", "/api/v1/users", {"email": email, "name": "New Person", "role": role}
    )
    assert status == 201, user
    return dict(user)


def test_admin_lists_users(deps: Deps) -> None:
    status, body = call(deps, "ada", "GET", "/api/v1/users")
    assert status == 200
    rows = {u["email"]: u for u in body["users"]}
    assert rows["v@example.com"]["role"] == "viewer" and rows["v@example.com"]["status"] == "active"


@pytest.mark.ac("AC-K1-1")
@pytest.mark.parametrize("who", ["mia", "vic"])
def test_only_admins_manage_users(deps: Deps, who: str) -> None:
    assert call(deps, who, "GET", "/api/v1/users")[0] == 403
    assert (
        call(deps, who, "POST", "/api/v1/users", {"email": "x@example.com", "name": "X", "role": "member"})[0]
        == 403
    )
    assert call(deps, who, "PATCH", f"/api/v1/users/{IDS['raj']}", {"role": "viewer"})[0] == 403


def test_invite_creates_an_invited_user_and_sends_the_cognito_email(deps: Deps) -> None:
    user = invite(deps, "New@Example.com")
    assert user["email"] == "new@example.com" and user["status"] == "invited" and user["role"] == "member"
    assert cognito(deps).invites_sent("new@example.com") == 1
    assert (
        call(
            deps,
            "ada",
            "POST",
            "/api/v1/users",
            {"email": "new@example.com", "name": "Again", "role": "member"},
        )[0]
        == 409
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": "nope", "name": "X", "role": "member"},
        {"email": "x@example.com", "name": "", "role": "member"},
        {"email": "x@example.com", "name": "X", "role": "guest"},
    ],
)
def test_invite_body_is_validated(deps: Deps, body: dict[str, Any]) -> None:
    assert call(deps, "ada", "POST", "/api/v1/users", body)[0] == 400


def test_invitee_sets_a_password_and_becomes_active(deps: Deps) -> None:
    invite(deps)
    temp = cognito(deps).last_temp_password("new@example.com")
    status, body, cookies = public(deps, "/api/auth/sign-in", {"email": "new@example.com", "password": temp})
    assert status == 200 and body["challenge"] == "new_password_required" and body["session"]
    assert not any(c.startswith("tl_rt=") for c in cookies)  # no session until the password is set
    status, body, cookies = public(
        deps,
        "/api/auth/accept-invite",
        {"email": "new@example.com", "session": body["session"], "new_password": NEW_PW},
    )
    assert status == 200 and body["access_token"] and any(c.startswith("tl_rt=") for c in cookies)
    rows = {u["email"]: u for u in call(deps, "ada", "GET", "/api/v1/users")[1]["users"]}
    assert rows["new@example.com"]["status"] == "active"


def test_accept_invite_rejects_a_weak_password(deps: Deps) -> None:
    invite(deps)
    temp = cognito(deps).last_temp_password("new@example.com")
    session = public(deps, "/api/auth/sign-in", {"email": "new@example.com", "password": temp})[1]["session"]
    status, body, _ = public(
        deps,
        "/api/auth/accept-invite",
        {"email": "new@example.com", "session": session, "new_password": "short"},
    )
    assert status == 400 and "new_password" in body["error"]["fields"]


@pytest.mark.ac("AC-F1-1")
def test_expired_invite_says_so_and_can_be_resent(deps: Deps) -> None:
    user = invite(deps)
    old = cognito(deps).last_temp_password("new@example.com")
    deps.clock.advance(days=7, seconds=1)  # type: ignore[attr-defined]
    status, body, _ = public(deps, "/api/auth/sign-in", {"email": "new@example.com", "password": old})
    assert status == 401 and body["error"]["code"] == "invite_expired"
    assert call(deps, "ada", "POST", f"/api/v1/users/{user['id']}/resend-invite")[0] == 200
    fresh = cognito(deps).last_temp_password("new@example.com")
    assert public(deps, "/api/auth/sign-in", {"email": "new@example.com", "password": fresh})[1]["challenge"]


def test_revoke_a_pending_invite(deps: Deps) -> None:
    user = invite(deps)
    assert call(deps, "ada", "DELETE", f"/api/v1/users/{user['id']}")[0] == 204
    assert cognito(deps).find_sub("new@example.com") is None
    assert all(u["email"] != "new@example.com" for u in call(deps, "ada", "GET", "/api/v1/users")[1]["users"])
    assert (
        call(deps, "ada", "DELETE", f"/api/v1/users/{IDS['raj']}")[0] == 409
    )  # active users are deactivated, not deleted


@pytest.mark.ac("AC-F7-5")
def test_role_change_refuses_the_next_write(deps: Deps) -> None:
    assert call(deps, "raj", "PATCH", "/api/v1/items/1001/values", {"values": {"note": "a"}})[0] == 200
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['raj']}", {"role": "viewer"})[0] == 200
    assert call(deps, "raj", "PATCH", "/api/v1/items/1001/values", {"values": {"note": "b"}})[0] == 403
    assert call(deps, "raj", "GET", "/api/v1/boards/10/schema")[1]["capabilities"] == ["post_updates", "read"]


@pytest.mark.ac("AC-F1-2")
def test_deactivated_user_is_locked_out_within_60_s(deps: Deps) -> None:
    rt = public(deps, "/api/auth/sign-in", {"email": "r@example.com", "password": "Existing-Password-1"})[2]
    assert call(deps, "raj", "GET", "/api/v1/me")[0] == 200
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['raj']}", {"status": "deactivated"})[0] == 200
    assert cognito(deps).is_enabled("r@example.com") is False
    deps.clock.advance(seconds=31)  # type: ignore[attr-defined]  # snapshot cache ≤ 30 s
    assert call(deps, "raj", "GET", "/api/v1/me")[0] == 401
    assert (
        public(deps, "/api/auth/sign-in", {"email": "r@example.com", "password": "Existing-Password-1"})[0]
        == 401
    )
    refreshed = [c for c in rt if c.startswith("tl_rt=")]
    from tests.integration.api.test_auth_routes import call as raw_call

    assert (
        raw_call(deps, "POST", "/api/auth/refresh", cookies=[refreshed[0].split(";")[0]], origin=None)[
            "statusCode"
        ]
        == 401
    )
    rows = {u["email"]: u for u in call(deps, "ada", "GET", "/api/v1/users")[1]["users"]}
    assert (
        rows["r@example.com"]["status"] == "deactivated" and rows["r@example.com"]["name"] == "Raj"
    )  # kept (F1.3)
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['raj']}", {"status": "active"})[0] == 200
    assert cognito(deps).is_enabled("r@example.com") is True


def test_last_admin_is_kept(deps: Deps) -> None:
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['ada']}", {"role": "member"})[0] == 409  # F1.4
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['ada']}", {"status": "deactivated"})[0] == 409
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['mia']}", {"role": "admin"})[0] == 200
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['ada']}", {"role": "member"})[0] == 200


def test_patch_validates(deps: Deps) -> None:
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['raj']}", {"role": "boss"})[0] == 400
    assert call(deps, "ada", "PATCH", f"/api/v1/users/{IDS['raj']}", {"status": "gone"})[0] == 400
    assert call(deps, "ada", "PATCH", "/api/v1/users/999999", {"role": "viewer"})[0] == 404


def test_invite_keeps_the_7_day_window_in_the_fake(deps: Deps) -> None:
    invite(deps)
    temp = cognito(deps).last_temp_password("new@example.com")
    deps.clock.advance(days=6, hours=23)  # type: ignore[attr-defined]
    assert public(deps, "/api/auth/sign-in", {"email": "new@example.com", "password": temp})[1]["challenge"]
