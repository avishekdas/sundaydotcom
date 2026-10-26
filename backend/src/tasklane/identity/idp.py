"""IdentityProvider port (Cognito behind the auth proxy, ADR-013). Admin operations only; sign-in is M1."""

from __future__ import annotations

import contextlib
import uuid
from typing import Any, Protocol


class UserExists(ValueError):
    pass


class IdentityProvider(Protocol):
    def create_user(self, email: str, name: str) -> str: ...
    def disable(self, email: str) -> None: ...
    def enable(self, email: str) -> None: ...
    def is_enabled(self, email: str) -> bool: ...
    def global_sign_out(self, email: str) -> None: ...
    def set_password(self, email: str, password: str) -> None: ...
    def find_sub(self, email: str) -> str | None: ...
    def invite(self, email: str, name: str) -> str: ...
    def resend_invite(self, email: str) -> None: ...
    def delete_user(self, email: str) -> None: ...


class CognitoIdp:
    """Emails are lower-cased (the pool is case-insensitive, `sign_in_case_sensitive=False`)."""

    def __init__(self, client: Any, pool_id: str) -> None:
        self._c, self._pool = client, pool_id

    def create_user(self, email: str, name: str) -> str:
        try:
            res = self._c.admin_create_user(
                UserPoolId=self._pool,
                Username=email.lower(),
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": email.lower()},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": name},
                ],
            )
        except self._c.exceptions.UsernameExistsException:
            raise UserExists(email) from None
        attrs = {a["Name"]: a["Value"] for a in res["User"]["Attributes"]}
        return str(attrs["sub"])

    def disable(self, email: str) -> None:
        self._c.admin_disable_user(UserPoolId=self._pool, Username=email.lower())

    def enable(self, email: str) -> None:
        self._c.admin_enable_user(UserPoolId=self._pool, Username=email.lower())

    def is_enabled(self, email: str) -> bool:
        return bool(self._c.admin_get_user(UserPoolId=self._pool, Username=email.lower())["Enabled"])

    def global_sign_out(self, email: str) -> None:
        self._c.admin_user_global_sign_out(UserPoolId=self._pool, Username=email.lower())

    def invite(self, email: str, name: str) -> str:
        """Cognito emails a temporary password with the pool's invitation template (D-054, F1.1: 7 days)."""
        try:
            res = self._c.admin_create_user(
                UserPoolId=self._pool,
                Username=email.lower(),
                DesiredDeliveryMediums=["EMAIL"],
                UserAttributes=[
                    {"Name": "email", "Value": email.lower()},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": name},
                ],
            )
        except self._c.exceptions.UsernameExistsException:
            raise UserExists(email) from None
        attrs = {a["Name"]: a["Value"] for a in res["User"]["Attributes"]}
        return str(attrs["sub"])

    def resend_invite(self, email: str) -> None:
        self._c.admin_create_user(
            UserPoolId=self._pool,
            Username=email.lower(),
            MessageAction="RESEND",
            DesiredDeliveryMediums=["EMAIL"],
        )

    def delete_user(self, email: str) -> None:
        with contextlib.suppress(self._c.exceptions.UserNotFoundException):
            self._c.admin_delete_user(UserPoolId=self._pool, Username=email.lower())

    def set_password(self, email: str, password: str) -> None:
        self._c.admin_set_user_password(
            UserPoolId=self._pool, Username=email.lower(), Password=password, Permanent=True
        )

    def find_sub(self, email: str) -> str | None:
        try:
            res = self._c.admin_get_user(UserPoolId=self._pool, Username=email.lower())
        except self._c.exceptions.UserNotFoundException:
            return None
        return next((str(a["Value"]) for a in res["UserAttributes"] if a["Name"] == "sub"), None)


class FakeIdp:
    def __init__(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}

    def create_user(self, email: str, name: str) -> str:
        key = email.lower()
        if key in self.users:
            raise UserExists(email)
        sub = str(uuid.uuid4())
        self.users[key] = {"sub": sub, "name": name, "enabled": True, "signed_out": 0}
        return sub

    def disable(self, email: str) -> None:
        self.users[email.lower()]["enabled"] = False

    def enable(self, email: str) -> None:
        self.users[email.lower()]["enabled"] = True

    def is_enabled(self, email: str) -> bool:
        return bool(self.users[email.lower()]["enabled"])

    def global_sign_out(self, email: str) -> None:
        self.users[email.lower()]["signed_out"] += 1

    def set_password(self, email: str, password: str) -> None:
        self.users[email.lower()]["password"] = password

    def find_sub(self, email: str) -> str | None:
        user = self.users.get(email.lower())
        return None if user is None else str(user["sub"])

    def invite(self, email: str, name: str) -> str:
        return self.create_user(email, name)

    def resend_invite(self, email: str) -> None:
        self.users[email.lower()]["invited"] = self.users[email.lower()].get("invited", 0) + 1

    def delete_user(self, email: str) -> None:
        self.users.pop(email.lower(), None)
