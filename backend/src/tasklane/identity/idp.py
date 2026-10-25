"""IdentityProvider port (Cognito behind the auth proxy, ADR-013). Admin operations only; sign-in is M1."""

from __future__ import annotations

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


class CognitoIdp:
    def __init__(self, client: Any, pool_id: str) -> None:
        self._c, self._pool = client, pool_id

    def create_user(self, email: str, name: str) -> str:
        try:
            res = self._c.admin_create_user(
                UserPoolId=self._pool,
                Username=email,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": name},
                ],
            )
        except self._c.exceptions.UsernameExistsException:
            raise UserExists(email) from None
        attrs = {a["Name"]: a["Value"] for a in res["User"]["Attributes"]}
        return str(attrs["sub"])

    def disable(self, email: str) -> None:
        self._c.admin_disable_user(UserPoolId=self._pool, Username=email)

    def enable(self, email: str) -> None:
        self._c.admin_enable_user(UserPoolId=self._pool, Username=email)

    def is_enabled(self, email: str) -> bool:
        return bool(self._c.admin_get_user(UserPoolId=self._pool, Username=email)["Enabled"])

    def global_sign_out(self, email: str) -> None:
        self._c.admin_user_global_sign_out(UserPoolId=self._pool, Username=email)


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
