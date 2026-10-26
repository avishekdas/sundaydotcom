"""Scripted dev test identities (PE-17, M0B-24, D-049).

admin / member / viewer / outsider exist in the IdP with a permanent password and as active `tl.users` rows linked
by `cognito_sub`; re-running keeps passwords and ids (CloudFormation re-invokes the custom resource on updates);
a user left in the IdP without stored credentials is adopted; prod is refused.
"""

from __future__ import annotations

import re

import pytest

from tasklane.identity.idp import FakeIdp
from tasklane.identity.test_identities import TEST_USERS, ProdRefused, ensure_test_identities
from tasklane.platform.db import StrictDataApiFake

ROLES = {"admin": "admin", "member": "member", "viewer": "viewer", "outsider": "member"}


def _rows(db: StrictDataApiFake) -> dict[str, dict[str, str]]:
    rows = db.query(
        "select id::text as id, email::text as email, role, status, cognito_sub::text as sub from tl.users"
    )
    return {r["email"]: r for r in rows}


def test_creates_four_users_in_idp_and_db(fresh_db: str) -> None:
    db, idp = StrictDataApiFake(fresh_db), FakeIdp()
    creds = ensure_test_identities(idp, db, stage="dev", existing={})
    assert set(creds) == set(ROLES) == {u.name for u in TEST_USERS}
    rows = _rows(db)
    for name, role in ROLES.items():
        email, password = creds[name]["email"], creds[name]["password"]
        assert email == f"tasklane-test-{name}@example.com"
        assert rows[email]["role"] == role and rows[email]["status"] == "active"
        assert rows[email]["sub"] == idp.find_sub(email)
        # pool policy: ≥ 12 chars, upper, lower, digit
        assert len(password) >= 16 and re.search("[A-Z]", password) and re.search("[a-z]", password)
        assert re.search("[0-9]", password)


def test_rerun_keeps_passwords_and_ids(fresh_db: str) -> None:
    db, idp = StrictDataApiFake(fresh_db), FakeIdp()
    first = ensure_test_identities(idp, db, stage="dev", existing={})
    ids = {e: r["id"] for e, r in _rows(db).items()}
    second = ensure_test_identities(idp, db, stage="dev", existing=first)
    assert second == first
    assert {e: r["id"] for e, r in _rows(db).items()} == ids


def test_adopts_idp_user_without_stored_credentials(fresh_db: str) -> None:
    db, idp = StrictDataApiFake(fresh_db), FakeIdp()
    sub = idp.create_user("tasklane-test-viewer@example.com", "Old")
    creds = ensure_test_identities(idp, db, stage="dev", existing={})
    assert _rows(db)["tasklane-test-viewer@example.com"]["sub"] == sub
    assert creds["viewer"]["password"]


def test_reactivates_a_deactivated_row(fresh_db: str) -> None:
    db, idp = StrictDataApiFake(fresh_db), FakeIdp()
    creds = ensure_test_identities(idp, db, stage="dev", existing={})
    db.execute("update tl.users set status = 'deactivated' where email = 'tasklane-test-member@example.com'")
    ensure_test_identities(idp, db, stage="dev", existing=creds)
    assert _rows(db)["tasklane-test-member@example.com"]["status"] == "active"


def test_prod_is_refused(fresh_db: str) -> None:
    with pytest.raises(ProdRefused):
        ensure_test_identities(FakeIdp(), StrictDataApiFake(fresh_db), stage="prod", existing={})
