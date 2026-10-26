"""User profile (A16, P1 basic): name, title, phone, timezone (empty → the account default)."""

from __future__ import annotations

from typing import Any

import pytest

from tasklane.api.app import Deps
from tests.integration.world import add_users, call, make_deps

pytestmark = pytest.mark.integration


@pytest.fixture
def deps(board_db: str) -> Deps:
    add_users(board_db)
    return make_deps(board_db)


def test_profile_round_trip(deps: Deps) -> None:
    status, me = call(
        deps,
        "raj",
        "PATCH",
        "/api/v1/me",
        {"name": "Raj Patel", "title": "Sales rep", "phone": "+1 734 844 2393", "timezone": "Asia/Kolkata"},
    )
    assert status == 200
    assert {k: me[k] for k in ("name", "title", "phone", "timezone")} == {
        "name": "Raj Patel",
        "title": "Sales rep",
        "phone": "+1 734 844 2393",
        "timezone": "Asia/Kolkata",
    }
    assert call(deps, "raj", "GET", "/api/v1/me")[1]["timezone"] == "Asia/Kolkata"


def test_timezone_falls_back_to_the_account(deps: Deps) -> None:
    call(deps, "ada", "PATCH", "/api/v1/account/settings", {"timezone": "America/New_York"})
    me = call(deps, "raj", "GET", "/api/v1/me")[1]
    assert me["timezone"] is None and me["effective_timezone"] == "America/New_York"
    call(deps, "raj", "PATCH", "/api/v1/me", {"timezone": "Europe/Paris"})
    assert call(deps, "raj", "GET", "/api/v1/me")[1]["effective_timezone"] == "Europe/Paris"
    call(deps, "raj", "PATCH", "/api/v1/me", {"timezone": None})
    assert call(deps, "raj", "GET", "/api/v1/me")[1]["effective_timezone"] == "America/New_York"


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "x" * 81},
        {"title": "x" * 101},
        {"phone": "x" * 41},
        {"timezone": "Mars/Base"},
        {"role": "admin"},
        {},
    ],
)
def test_profile_is_validated_and_role_is_not_self_service(deps: Deps, body: dict[str, Any]) -> None:
    assert call(deps, "raj", "PATCH", "/api/v1/me", body)[0] == 400
