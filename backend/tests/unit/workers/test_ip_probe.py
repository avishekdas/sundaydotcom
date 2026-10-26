"""AC-K7-2 on dev (D-046, M1 close): a dev-only λ is "IP B" — it signs in through CloudFront from AWS egress — and
clears one test user's sign-in counters so the check can run after every deploy. Refused for prod."""

from __future__ import annotations

from typing import Any

import pytest

from tasklane.workers.ip_probe import handler


class Http:
    def __init__(self, status: int) -> None:
        self.status, self.calls = status, []  # type: ignore[var-annotated]

    def __call__(self, url: str, body: dict[str, Any]) -> int:
        self.calls.append((url, body))
        return self.status


class Ddb:
    def __init__(self, keys: list[str]) -> None:
        self.keys, self.deleted = keys, []  # type: ignore[var-annotated]

    def scan(self, **kw: Any) -> dict[str, Any]:
        prefix = kw["ExpressionAttributeValues"][":p"]["S"]
        return {"Items": [{"pk": {"S": k}} for k in self.keys if k.startswith(prefix)]}

    def delete_item(self, **kw: Any) -> None:
        self.deleted.append(kw["Key"]["pk"]["S"])


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STAGE", "dev")
    monkeypatch.setenv("BASE_URL", "https://d.example.net")
    monkeypatch.setenv("COUNTERS_TABLE", "counters")


def test_sign_in_goes_through_cloudfront_and_reports_the_status() -> None:
    http = Http(200)
    res = handler({"action": "sign_in", "email": "o@example.com", "password": "pw"}, None, http=http)
    assert res["status"] == 200 and res["elapsed_s"] >= 0
    assert http.calls == [
        ("https://d.example.net/api/auth/sign-in", {"email": "o@example.com", "password": "pw"})
    ]


def test_clear_counters_deletes_only_that_users_sign_in_rows() -> None:
    ddb = Ddb(
        ["signin#o@example.com", "signin#o@example.com#203.0.113.1/32", "signin#x@example.com", "refresh#1"]
    )
    res = handler({"action": "clear_counters", "email": "O@example.com"}, None, ddb=ddb)
    assert sorted(ddb.deleted) == ["signin#o@example.com", "signin#o@example.com#203.0.113.1/32"]
    assert res == {"deleted": 2}


def test_refused_for_prod_and_unknown_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        handler({"action": "nope"}, None)
    monkeypatch.setenv("STAGE", "prod")
    with pytest.raises(PermissionError):
        handler({"action": "sign_in", "email": "a", "password": "b"}, None, http=Http(200))
