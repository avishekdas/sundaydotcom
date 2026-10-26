"""Auth backend port for the auth proxy (ADR-013): Cognito admin auth flows, or a fake that models what S-2b
measured (per-user counting, lock 2^(n-5) s after the n-th evaluated failure, attempts during a lock refused and not
counted, success resets)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from tasklane.platform.clock import Clock


@dataclass(frozen=True)
class Tokens:
    access_token: str
    expires_in: int
    refresh_token: str | None = None


class BadCredentials(Exception):
    """Wrong password or unknown user — indistinguishable on purpose (SEC-5)."""


class Locked(Exception):
    """Cognito's own per-user lock ("Password attempts exceeded")."""


class InvalidRefresh(Exception):
    pass


class AuthBackend(Protocol):
    def sign_in(self, email: str, password: str) -> Tokens: ...
    def refresh(self, refresh_token: str) -> Tokens: ...
    def revoke(self, refresh_token: str) -> None: ...
    def global_sign_out(self, email: str) -> None: ...


def _code(e: ClientError) -> tuple[str, str]:
    err = e.response.get("Error", {})
    return str(err.get("Code", "")), str(err.get("Message", ""))


class CognitoAuth:
    def __init__(self, client: Any, pool_id: str, client_id: str) -> None:
        self._c, self._pool, self._client_id = client, pool_id, client_id

    def sign_in(self, email: str, password: str) -> Tokens:
        try:
            res = self._c.admin_initiate_auth(
                UserPoolId=self._pool,
                ClientId=self._client_id,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email.strip().lower(), "PASSWORD": password},
            )
        except ClientError as e:
            code, msg = _code(e)
            if code == "NotAuthorizedException" and "attempts exceeded" in msg.lower():
                raise Locked from None
            if code in {"NotAuthorizedException", "UserNotFoundException", "PasswordResetRequiredException"}:
                raise BadCredentials from None
            raise
        result = res.get("AuthenticationResult")
        if not result:  # a challenge (e.g. NEW_PASSWORD_REQUIRED for invitees) is handled by later stories
            raise BadCredentials
        return Tokens(str(result["AccessToken"]), int(result["ExpiresIn"]), result.get("RefreshToken"))

    def refresh(self, refresh_token: str) -> Tokens:
        try:
            res = self._c.admin_initiate_auth(
                UserPoolId=self._pool,
                ClientId=self._client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters={"REFRESH_TOKEN": refresh_token},
            )
        except ClientError as e:
            if _code(e)[0] in {"NotAuthorizedException", "UserNotFoundException"}:
                raise InvalidRefresh from None
            raise
        result = res["AuthenticationResult"]
        return Tokens(str(result["AccessToken"]), int(result["ExpiresIn"]))

    def revoke(self, refresh_token: str) -> None:
        self._c.revoke_token(Token=refresh_token, ClientId=self._client_id)

    def global_sign_out(self, email: str) -> None:
        self._c.admin_user_global_sign_out(UserPoolId=self._pool, Username=email.strip().lower())


@dataclass
class _User:
    password: str
    failures: int = 0
    locked_until: datetime | None = None
    tokens: set[str] = field(default_factory=set)


class FakeAuthBackend:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._users: dict[str, _User] = {}
        self._refresh: dict[str, str] = {}
        self.calls = 0

    def add_user(self, email: str, password: str) -> None:
        self._users[email.lower()] = _User(password)

    def lock(self, email: str, *, seconds: float) -> None:
        """Test hook: a lock longer than the schedule (S-2b run 8 anomaly)."""
        self._users[email.lower()].locked_until = self._clock.now() + timedelta(seconds=seconds)

    def sign_in(self, email: str, password: str) -> Tokens:
        self.calls += 1
        user = self._users.get(email.strip().lower())
        if user is None:
            raise BadCredentials
        now = self._clock.now()
        if user.locked_until and now < user.locked_until:
            raise Locked
        if password != user.password:
            user.failures += 1
            if user.failures >= 5:
                user.locked_until = now + timedelta(seconds=2 ** (user.failures - 5))
            raise BadCredentials
        user.failures, user.locked_until = 0, None
        rt = secrets.token_urlsafe(16)
        user.tokens.add(rt)
        self._refresh[rt] = email.strip().lower()
        return Tokens(secrets.token_urlsafe(16), 1800, rt)

    def refresh(self, refresh_token: str) -> Tokens:
        email = self._refresh.get(refresh_token)
        if email is None or refresh_token not in self._users[email].tokens:
            raise InvalidRefresh
        return Tokens(secrets.token_urlsafe(16), 1800)

    def revoke(self, refresh_token: str) -> None:
        email = self._refresh.get(refresh_token)
        if email:
            self._users[email].tokens.discard(refresh_token)

    def global_sign_out(self, email: str) -> None:
        user = self._users.get(email.strip().lower())
        if user:
            user.tokens.clear()
