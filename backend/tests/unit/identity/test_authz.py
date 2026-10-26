"""Authorization as data (ADR-008, arch 07 §7.2, requirements K1/K3 tables).

caps(user, board) = OWNER_CAPS if owner (or Admin, K1.1/K3.1) else PERMISSION_SET_CAPS[set], then ∩ ROLE_CEILING[role].
`edit_assigned` needs the item-level guard of M2 (DL-5); until then it grants no value edits (safe deny).
"""

from __future__ import annotations

import pytest

from tasklane.identity.authz import (
    ACCOUNT_CAPS,
    BOARD_CAPS,
    AccountCap,
    Cap,
    account_caps,
    board_caps,
)

ALL = BOARD_CAPS
R, V, S, C, U, L = (
    Cap.READ,
    Cap.EDIT_VALUES,
    Cap.EDIT_STRUCTURE,
    Cap.CREATE_DELETE_ITEMS,
    Cap.POST_UPDATES,
    Cap.LOG_ACTIVITIES,
)

# requirements K3 table (non-owners), Member role
K3 = {
    "edit_everything": {R, V, S, C, U, L},
    "edit_content": {R, V, C, U, L},
    "view_comment": {R, U, L},
    "edit_assigned": {R, U, L},  # value/create rights arrive with the M2 item guard
}


@pytest.mark.parametrize(("pset", "expected"), K3.items())
def test_member_non_owner_follows_the_k3_table(pset: str, expected: set[Cap]) -> None:
    assert board_caps("member", is_owner=False, permission_set=pset) == frozenset(expected)


@pytest.mark.parametrize("pset", K3)
def test_owners_and_admins_have_full_rights(pset: str) -> None:
    assert board_caps("member", is_owner=True, permission_set=pset) == ALL  # K3.1
    assert board_caps("admin", is_owner=False, permission_set=pset) == ALL  # K1.1


@pytest.mark.ac("AC-K3-3")
@pytest.mark.parametrize("pset", K3)
@pytest.mark.parametrize("owner", [False, True])
def test_viewer_never_edits(pset: str, owner: bool) -> None:
    """K1.2: a Viewer can never edit values or structure, whatever the board says; may post updates only (K3.4)."""
    assert board_caps("viewer", is_owner=owner, permission_set=pset) == frozenset({R, U})


def test_account_capabilities_follow_k1() -> None:
    assert account_caps("admin") == ACCOUNT_CAPS
    assert account_caps("member") == frozenset(
        {AccountCap.CREATE_WORKSPACE, AccountCap.CREATE_BOARD, AccountCap.EXPORT}
    )
    assert account_caps("viewer") == frozenset()
    assert account_caps("guest") == frozenset()


def test_unknown_role_or_set_gets_nothing() -> None:
    assert board_caps("intruder", is_owner=True, permission_set="edit_everything") == frozenset()
    assert board_caps("member", is_owner=False, permission_set="bogus") == frozenset()
