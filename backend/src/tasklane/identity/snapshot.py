"""PermissionSnapshot (arch 07 §7.2): who the caller is and what they can do, loaded with one SQL statement and
cached in Lambda memory for at most 30 s. Writes never trust the cache alone: the Mutation's epoch guard (SEC-3)
refuses a write whose snapshot predates a permission change, and the caller reloads and retries once (FR-9)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from tasklane.identity.authz import AccountCap, Cap, account_caps, board_caps
from tasklane.identity.visibility import snapshot_sql
from tasklane.platform.clock import Clock
from tasklane.platform.db import Db

TTL = timedelta(seconds=30)


@dataclass(frozen=True)
class BoardAccess:
    permission_set: str
    is_owner: bool
    admin_override: bool = False  # visible only because the caller is an Admin (K1.1, audited)


@dataclass(frozen=True)
class PermissionSnapshot:
    user_id: int
    name: str
    email: str
    role: str
    tokens_valid_after: int  # epoch seconds (token iat has 1 s resolution, FR-11)
    epoch: int
    boards: dict[int, BoardAccess]

    def caps(self, board_id: int) -> frozenset[Cap] | None:
        """None → the board is not visible (callers answer 404, no existence leak)."""
        access = self.boards.get(board_id)
        if access is None:
            return None
        return board_caps(self.role, is_owner=access.is_owner, permission_set=access.permission_set)

    def account_caps(self) -> frozenset[AccountCap]:
        return account_caps(self.role)


def load_snapshot(db: Db, cognito_sub: str) -> PermissionSnapshot | None:
    sql, params = snapshot_sql(cognito_sub)
    doc = json.loads(db.query(sql, params)[0]["doc"])
    u = doc["user"]
    if u is None:
        return None
    return PermissionSnapshot(
        user_id=int(u["id"]),
        name=u["name"],
        email=u["email"],
        role=u["role"],
        tokens_valid_after=int(u["tva"]),
        epoch=int(doc["epoch"]),
        boards={
            int(b): BoardAccess(pset, bool(owner), bool(override))
            for b, pset, owner, override in doc["boards"]
        },
    )


class SnapshotCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[PermissionSnapshot, datetime]] = {}

    def get(
        self, db: Db, clock: Clock, cognito_sub: str, *, fresh: bool = False
    ) -> PermissionSnapshot | None:
        now = clock.now()
        hit = self._items.get(cognito_sub)
        if hit and not fresh and now - hit[1] < TTL:
            return hit[0]
        snap = load_snapshot(db, cognito_sub)
        if snap is None:
            self._items.pop(cognito_sub, None)
            return None
        self._items[cognito_sub] = (snap, now)
        return snap

    def clear(self) -> None:
        self._items.clear()
