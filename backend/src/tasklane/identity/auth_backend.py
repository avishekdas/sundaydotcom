"""Auth backend port for the auth proxy (ADR-013): Cognito admin auth flows, or a fake that models what S-2b
measured (per-user counting, lock 2^(n-5) s after the n-th evaluated failure, attempts during a lock refused and not
counted, success resets)."""

from __future__ import annotations

import secrets
import uuid
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


class BadCode(Exception):
    """Wrong, expired or over-used reset code — also used for unknown emails (SEC-5)."""


class NewPasswordRequired(Exception):
    """First sign-in of an invitee (K7.6, F1.2): Cognito's NEW_PASSWORD_REQUIRED challenge."""

    def __init__(self, session: str) -> None:
        super().__init__("new password required")
        self.session = session


class InviteExpired(Exception):
    """The invitation's temporary password is older than its validity (F1.1: 7 days)."""


class WeakPassword(Exception):
    """The new password breaks the pool policy (≥ 12 chars, upper, lower, digit)."""


class AuthBackend(Protocol):
    def sign_in(self, email: str, password: str) -> Tokens: ...
    def refresh(self, refresh_token: str) -> Tokens: ...
    def revoke(self, refresh_token: str) -> None: ...
    def global_sign_out(self, email: str) -> None: ...
    def forgot(self, email: str) -> None: ...
    def confirm_reset(self, email: str, code: str, new_password: str) -> None: ...
    def complete_new_password(self, email: str, session: str, new_password: str) -> Tokens: ...


INVITE_VALID = timedelta(days=7)


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
            if code == "NotAuthorizedException" and "temporary password has expired" in msg.lower():
                raise InviteExpired from None
            if code in {"NotAuthorizedException", "UserNotFoundException", "PasswordResetRequiredException"}:
                raise BadCredentials from None
            raise
        if res.get("ChallengeName") == "NEW_PASSWORD_REQUIRED":
            raise NewPasswordRequired(str(res["Session"]))
        result = res.get("AuthenticationResult")
        if not result:  # other challenges (MFA) are not enabled (D-045)
            raise BadCredentials
        return Tokens(str(result["AccessToken"]), int(result["ExpiresIn"]), result.get("RefreshToken"))

    def complete_new_password(self, email: str, session: str, new_password: str) -> Tokens:
        try:
            res = self._c.admin_respond_to_auth_challenge(
                UserPoolId=self._pool,
                ClientId=self._client_id,
                ChallengeName="NEW_PASSWORD_REQUIRED",
                Session=session,
                ChallengeResponses={"USERNAME": email.strip().lower(), "NEW_PASSWORD": new_password},
            )
        except ClientError as e:
            name, msg = _code(e)
            if name == "InvalidPasswordException":
                raise WeakPassword(msg) from None
            if name in {"NotAuthorizedException", "CodeMismatchException", "ExpiredCodeException"}:
                raise BadCredentials from None
            raise
        result = res["AuthenticationResult"]
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

    def forgot(self, email: str) -> None:
        """Cognito emails the code (D-047). Unknown users and Cognito's own limits stay silent (SEC-5)."""
        try:
            self._c.forgot_password(ClientId=self._client_id, Username=email.strip().lower())
        except ClientError as e:
            if _code(e)[0] not in {
                "UserNotFoundException",
                "LimitExceededException",
                "InvalidParameterException",  # no verified email
                "NotAuthorizedException",
            }:
                raise

    def confirm_reset(self, email: str, code: str, new_password: str) -> None:
        try:
            self._c.confirm_forgot_password(
                ClientId=self._client_id,
                Username=email.strip().lower(),
                ConfirmationCode=code,
                Password=new_password,
            )
        except ClientError as e:
            name, msg = _code(e)
            if name == "InvalidPasswordException":
                raise WeakPassword(msg) from None
            if name in {
                "CodeMismatchException",
                "ExpiredCodeException",
                "UserNotFoundException",
                "LimitExceededException",
                "TooManyFailedAttemptsException",
                "NotAuthorizedException",
            }:
                raise BadCode from None
            raise


@dataclass
class _User:
    password: str
    failures: int = 0
    locked_until: datetime | None = None
    tokens: set[str] = field(default_factory=set)
    sub: str = field(default_factory=lambda: str(uuid.uuid4()))
    enabled: bool = True
    invited_at: datetime | None = None  # set while the temporary password is pending (FORCE_CHANGE_PASSWORD)
    invites: int = 0


class FakeAuthBackend:
    """Fake Cognito for Tier A: the sign-in side (AuthBackend) and the admin side (IdentityProvider) share one
    user store, so invites can be accepted end to end."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._users: dict[str, _User] = {}
        self._refresh: dict[str, str] = {}
        self._codes: dict[str, str] = {}
        self._sent: dict[str, int] = {}
        self._sessions: dict[str, str] = {}
        self.calls = 0

    def add_user(self, email: str, password: str) -> None:
        self._users[email.lower()] = _User(password)

    def lock(self, email: str, *, seconds: float) -> None:
        """Test hook: a lock longer than the schedule (S-2b run 8 anomaly)."""
        self._users[email.lower()].locked_until = self._clock.now() + timedelta(seconds=seconds)

    def sign_in(self, email: str, password: str) -> Tokens:
        self.calls += 1
        user = self._users.get(email.strip().lower())
        if user is None or not user.enabled:
            raise BadCredentials
        now = self._clock.now()
        if user.locked_until and now < user.locked_until:
            raise Locked
        if user.invited_at is not None:
            if now - user.invited_at > INVITE_VALID:
                raise InviteExpired
            if password == user.password:
                session = secrets.token_urlsafe(16)
                self._sessions[session] = email.strip().lower()
                raise NewPasswordRequired(session)
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

    def forgot(self, email: str) -> None:
        key = email.strip().lower()
        if key in self._users:
            self._codes[key] = f"{secrets.randbelow(10**6):06d}"
            self._sent[key] = self._sent.get(key, 0) + 1

    def confirm_reset(self, email: str, code: str, new_password: str) -> None:
        key = email.strip().lower()
        if key not in self._users or self._codes.get(key) != code:
            raise BadCode
        if not _policy_ok(new_password):
            raise WeakPassword("Password must be at least 12 characters with upper, lower case and a digit")
        self._users[key].password = new_password
        del self._codes[key]

    # test helpers
    def last_code(self, email: str) -> str:
        return self._codes[email.strip().lower()]

    def codes_sent(self, email: str) -> int:
        return self._sent.get(email.strip().lower(), 0)

    def complete_new_password(self, email: str, session: str, new_password: str) -> Tokens:
        key = email.strip().lower()
        if self._sessions.get(session) != key:
            raise BadCredentials
        if not _policy_ok(new_password):
            raise WeakPassword("Password must be at least 12 characters with upper, lower case and a digit")
        del self._sessions[session]
        user = self._users[key]
        user.password, user.invited_at = new_password, None
        return self.sign_in(key, new_password)

    # --- IdentityProvider (admin side) ---
    def create_user(self, email: str, name: str) -> str:
        from tasklane.identity.idp import UserExists

        key = email.strip().lower()
        if key in self._users:
            raise UserExists(email)
        self._users[key] = _User(password=secrets.token_urlsafe(24))
        return self._users[key].sub

    def invite(self, email: str, name: str) -> str:
        sub = self.create_user(email, name)
        self.resend_invite(email)
        return sub

    def resend_invite(self, email: str) -> None:
        user = self._users[email.strip().lower()]
        user.password = f"Tmp-{secrets.token_urlsafe(9)}9a"
        user.invited_at = self._clock.now()
        user.invites += 1

    def delete_user(self, email: str) -> None:
        self._users.pop(email.strip().lower(), None)

    def disable(self, email: str) -> None:
        self._users[email.strip().lower()].enabled = False

    def enable(self, email: str) -> None:
        self._users[email.strip().lower()].enabled = True

    def is_enabled(self, email: str) -> bool:
        return self._users[email.strip().lower()].enabled

    def set_password(self, email: str, password: str) -> None:
        user = self._users[email.strip().lower()]
        user.password, user.invited_at = password, None

    def find_sub(self, email: str) -> str | None:
        user = self._users.get(email.strip().lower())
        return None if user is None else user.sub

    # test helpers
    def last_temp_password(self, email: str) -> str:
        return self._users[email.strip().lower()].password

    def invites_sent(self, email: str) -> int:
        user = self._users.get(email.strip().lower())
        return 0 if user is None else user.invites


def _policy_ok(pw: str) -> bool:
    return (
        len(pw) >= 12
        and any(c.isupper() for c in pw)
        and any(c.islower() for c in pw)
        and any(c.isdigit() for c in pw)
    )
