"""Bootstrap at deployment (K7.6, A1.1, A2.3, D-055): the configured email is an Admin and a default workspace exists.

Idempotent, so it can run on every deploy: an existing row is promoted to Admin (status kept), a Cognito user with
no row is adopted as active, and only a brand-new person gets the Cognito invitation email (set password on first
sign-in). An existing default workspace is kept as it is.
"""

from __future__ import annotations

from tasklane.identity.idp import IdentityProvider
from tasklane.platform.db import Db

DEFAULT_WORKSPACE = "Main workspace"


def ensure_bootstrap(db: Db, idp: IdentityProvider, email: str, name: str = "Admin") -> None:
    email = email.strip().lower()
    if db.query("select 1 as x from tl.users where email = :e", {"e": email}):
        db.execute("update tl.users set role = 'admin', updated_at = now() where email = :e", {"e": email})
    else:
        sub = idp.find_sub(email)
        status = "active" if sub else "invited"
        if sub is None:
            sub = idp.invite(email, name)
        db.execute(
            "insert into tl.users (cognito_sub, email, name, role, status) values (:s::uuid, :e, :n, 'admin', :st)",
            {"s": sub, "e": email, "n": name, "st": status},
        )
    db.execute(
        """insert into tl.workspaces (name, kind, position, is_default)
           select :n, 'open', 'a', true
           where not exists (select 1 from tl.workspaces where is_default and state = 'active')""",
        {"n": DEFAULT_WORKSPACE},
    )
    db.execute("update tl.account set perm_epoch = perm_epoch + 1")
