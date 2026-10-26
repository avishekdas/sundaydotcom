"""Scripted dev test identities (PE-17, M0B-24, D-049): admin, member, viewer and outsider.

Each exists in the IdP with a permanent password and as an active `tl.users` row linked by `cognito_sub`.
Idempotent: stored credentials are reused, an IdP user without stored credentials is adopted, a deactivated row is
reactivated. Never runs for prod.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass

from tasklane.identity.idp import IdentityProvider
from tasklane.platform.db import Db


class ProdRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class Identity:
    name: str
    role: str

    @property
    def email(self) -> str:
        return f"tasklane-test-{self.name}@example.com"


# outsider: a Member who is given no workspace or board membership by the tests that use it
TEST_USERS = (
    Identity("admin", "admin"),
    Identity("member", "member"),
    Identity("viewer", "viewer"),
    Identity("outsider", "member"),
)

Credentials = dict[str, dict[str, str]]


def new_password() -> str:
    # ≥ 12 chars with upper, lower and digit (pool policy); 18 random bytes ≈ 144 bits
    return f"{secrets.token_urlsafe(18)}Aa9"


def ensure_test_identities(
    idp: IdentityProvider,
    db: Db,
    *,
    stage: str,
    existing: Credentials,
    password_factory: Callable[[], str] = new_password,
) -> Credentials:
    if stage == "prod":
        raise ProdRefused("test identities are never created in prod")
    out: Credentials = {}
    for user in TEST_USERS:
        password = (existing.get(user.name) or {}).get("password") or password_factory()
        display = f"Test {user.name.title()}"
        sub = idp.find_sub(user.email) or idp.create_user(user.email, display)
        idp.set_password(user.email, password)
        db.execute(
            """insert into tl.users (cognito_sub, email, name, role, status)
               values (:sub::uuid, :email, :name, :role, 'active')
               on conflict (email) do update
                 set cognito_sub = excluded.cognito_sub, role = excluded.role, status = 'active', updated_at = now()""",
            {"sub": sub, "email": user.email, "name": display, "role": user.role},
        )
        out[user.name] = {"email": user.email, "password": password}
    return out
