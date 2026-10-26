"""Cognito adapter of the auth backend: error mapping (S-2b messages) and the calls it makes."""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError

from tasklane.identity.auth_backend import BadCredentials, CognitoAuth, InvalidRefresh, Locked


class Stub:
    def __init__(self, error: tuple[str, str] | None = None) -> None:
        self.error, self.calls = error, []  # type: ignore[var-annotated]

    def _maybe_fail(self, op: str) -> None:
        if self.error:
            raise ClientError({"Error": {"Code": self.error[0], "Message": self.error[1]}}, op)

    def admin_initiate_auth(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("admin_initiate_auth", kw))
        self._maybe_fail("AdminInitiateAuth")
        return {"AuthenticationResult": {"AccessToken": "at", "ExpiresIn": 1800, "RefreshToken": "rt"}}

    def revoke_token(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("revoke_token", kw))
        return {}

    def forgot_password(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("forgot_password", kw))
        self._maybe_fail("ForgotPassword")
        return {}

    def confirm_forgot_password(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("confirm_forgot_password", kw))
        self._maybe_fail("ConfirmForgotPassword")
        return {}

    def admin_user_global_sign_out(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("admin_user_global_sign_out", kw))
        return {}


@pytest.mark.parametrize(
    ("error", "exc"),
    [
        (("NotAuthorizedException", "Incorrect username or password."), BadCredentials),
        (("UserNotFoundException", "User does not exist."), BadCredentials),
        (("NotAuthorizedException", "Password attempts exceeded"), Locked),
    ],
)
def test_sign_in_error_mapping(error: tuple[str, str], exc: type[Exception]) -> None:
    with pytest.raises(exc):
        CognitoAuth(Stub(error), "pool", "client").sign_in("a@example.com", "x")


def test_sign_in_uses_admin_password_flow_with_lowercased_email() -> None:
    s = Stub()
    t = CognitoAuth(s, "pool", "client").sign_in("A@Example.com", "pw")
    assert (t.access_token, t.refresh_token) == ("at", "rt")
    _op, kw = s.calls[0]
    assert (
        kw["AuthFlow"] == "ADMIN_USER_PASSWORD_AUTH" and kw["AuthParameters"]["USERNAME"] == "a@example.com"
    )


def test_refresh_errors_map_to_invalid_refresh() -> None:
    with pytest.raises(InvalidRefresh):
        CognitoAuth(Stub(("NotAuthorizedException", "Refresh Token has been revoked")), "p", "c").refresh(
            "rt"
        )


def test_revoke_and_global_sign_out() -> None:
    s = Stub()
    a = CognitoAuth(s, "pool", "client")
    a.revoke("rt")
    a.global_sign_out("A@example.com")
    assert [c[0] for c in s.calls] == ["revoke_token", "admin_user_global_sign_out"]
    assert s.calls[1][1]["Username"] == "a@example.com"


def test_forgot_swallows_unknown_users_and_reset_maps_errors() -> None:
    from tasklane.identity.auth_backend import BadCode, WeakPassword

    CognitoAuth(Stub(("UserNotFoundException", "x")), "p", "c").forgot("a@example.com")
    with pytest.raises(BadCode):
        CognitoAuth(Stub(("CodeMismatchException", "x")), "p", "c").confirm_reset("a@example.com", "1", "pw")
    with pytest.raises(BadCode):
        CognitoAuth(Stub(("ExpiredCodeException", "x")), "p", "c").confirm_reset("a@example.com", "1", "pw")
    with pytest.raises(BadCode):
        CognitoAuth(Stub(("UserNotFoundException", "x")), "p", "c").confirm_reset("a@example.com", "1", "pw")
    with pytest.raises(WeakPassword):
        CognitoAuth(Stub(("InvalidPasswordException", "Password did not conform")), "p", "c").confirm_reset(
            "a@example.com", "1", "pw"
        )


def test_new_password_challenge_and_expired_invite() -> None:
    from tasklane.identity.auth_backend import InviteExpired, NewPasswordRequired

    class Challenge(Stub):
        def admin_initiate_auth(self, **kw: Any) -> dict[str, Any]:
            return {"ChallengeName": "NEW_PASSWORD_REQUIRED", "Session": "sess-1"}

        def admin_respond_to_auth_challenge(self, **kw: Any) -> dict[str, Any]:
            self.calls.append(("admin_respond_to_auth_challenge", kw))
            return {"AuthenticationResult": {"AccessToken": "at", "ExpiresIn": 1800, "RefreshToken": "rt"}}

    with pytest.raises(NewPasswordRequired) as e:
        CognitoAuth(Challenge(), "p", "c").sign_in("A@example.com", "temp")
    assert e.value.session == "sess-1"
    s = Challenge()
    t = CognitoAuth(s, "p", "c").complete_new_password("A@example.com", "sess-1", "Brand-New-Password-7")
    assert t.refresh_token == "rt"
    kw = s.calls[0][1]
    assert (
        kw["ChallengeName"] == "NEW_PASSWORD_REQUIRED"
        and kw["ChallengeResponses"]["USERNAME"] == "a@example.com"
    )
    msg = "Temporary password has expired and must be reset by an administrator."
    with pytest.raises(InviteExpired):
        CognitoAuth(Stub(("NotAuthorizedException", msg)), "p", "c").sign_in("a@example.com", "temp")
