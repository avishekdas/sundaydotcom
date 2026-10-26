"""Authorization as data (ADR-008, arch 07 §7.2; requirements K1 and K3 tables).

Pure functions — no I/O. Board capabilities for a user on a board:
``OWNER_CAPS`` if the user owns it (K3.1) or is an Admin (K1.1), else ``PERMISSION_SET_CAPS[set]``; then intersected
with the role ceiling (a Viewer never edits, K1.2). The same tables drive the generated route matrix (AC-K3-4).
"""

from __future__ import annotations

from enum import StrEnum


class Cap(StrEnum):
    READ = "read"
    EDIT_VALUES = "edit_values"
    EDIT_STRUCTURE = "edit_structure"  # columns, groups, views, settings
    CREATE_DELETE_ITEMS = "create_delete_items"
    POST_UPDATES = "post_updates"
    LOG_ACTIVITIES = "log_activities"


class AccountCap(StrEnum):
    MANAGE_ACCOUNT = "manage_account"  # settings, users, roles, security, audit
    CREATE_WORKSPACE = "create_workspace"
    CREATE_BOARD = "create_board"
    INVITE = "invite"
    EXPORT = "export"


BOARD_CAPS = frozenset(Cap)
ACCOUNT_CAPS = frozenset(AccountCap)
OWNER_CAPS = BOARD_CAPS

PERMISSION_SET_CAPS: dict[str, frozenset[Cap]] = {
    "edit_everything": BOARD_CAPS,
    "edit_content": frozenset(BOARD_CAPS - {Cap.EDIT_STRUCTURE}),
    "view_comment": frozenset({Cap.READ, Cap.POST_UPDATES, Cap.LOG_ACTIVITIES}),
    # value edits and creates depend on the item's assignment column: the item-level guard arrives in M2 (DL-5);
    # until then the set grants only what needs no item check (safe deny)
    "edit_assigned": frozenset({Cap.READ, Cap.POST_UPDATES, Cap.LOG_ACTIVITIES}),
}

ROLE_CEILING: dict[str, frozenset[Cap]] = {
    "admin": BOARD_CAPS,
    "member": BOARD_CAPS,
    "viewer": frozenset({Cap.READ, Cap.POST_UPDATES}),  # K1.2, K3.4: may post updates, not log activities
    "guest": frozenset(BOARD_CAPS - {Cap.EDIT_STRUCTURE}),  # P2: shareable boards only (visibility decides)
}

ROLE_ACCOUNT_CAPS: dict[str, frozenset[AccountCap]] = {
    "admin": ACCOUNT_CAPS,
    "member": frozenset({AccountCap.CREATE_WORKSPACE, AccountCap.CREATE_BOARD, AccountCap.EXPORT}),
    "viewer": frozenset(),
    "guest": frozenset(),
}


def board_caps(role: str, *, is_owner: bool, permission_set: str) -> frozenset[Cap]:
    ceiling = ROLE_CEILING.get(role, frozenset())
    if role == "admin" or is_owner:
        return OWNER_CAPS & ceiling
    return PERMISSION_SET_CAPS.get(permission_set, frozenset()) & ceiling


def account_caps(role: str) -> frozenset[AccountCap]:
    return ROLE_ACCOUNT_CAPS.get(role, frozenset())
