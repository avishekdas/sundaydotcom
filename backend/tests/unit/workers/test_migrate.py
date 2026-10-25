"""migrate λ (PE-4): reads secrets, applies migrations via the Db port, enables role logins (M0A-3)."""

from __future__ import annotations

import json
from typing import Any

from tasklane.workers import migrate


class FakeSecrets:
    def __init__(self, values: dict[str, dict[str, str]]) -> None:
        self.values = values

    def get_secret_value(self, SecretId: str) -> dict[str, Any]:
        return {"SecretString": json.dumps(self.values[SecretId])}


def test_handler_wires_db_migrations_and_role_passwords(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setenv("CLUSTER_ARN", "arn:cluster")
    monkeypatch.setenv("ADMIN_SECRET_ARN", "arn:admin")
    monkeypatch.setenv("DB_NAME", "tasklane")
    monkeypatch.setenv("ROLE_SECRET_ARNS", json.dumps({"tl_api_rw": "arn:api", "tl_reader": "arn:reader"}))
    secrets = FakeSecrets(
        {
            "arn:api": {"username": "tl_api_rw", "password": "p1"},
            "arn:reader": {"username": "tl_reader", "password": "p2"},
        }
    )

    def fake_apply(db: Any, directory: Any) -> list[str]:
        seen["db"] = db
        seen["dir"] = directory
        return ["0000", "0001"]

    def fake_logins(db: Any, passwords: dict[str, str]) -> None:
        seen["passwords"] = passwords

    monkeypatch.setattr(migrate, "apply_migrations", fake_apply)
    monkeypatch.setattr(migrate, "ensure_role_logins", fake_logins)
    out = migrate.handler({}, None, rds_client=object(), secrets_client=secrets)
    assert out == {"applied": ["0000", "0001"], "roles": ["tl_api_rw", "tl_reader"]}
    assert seen["passwords"] == {"tl_api_rw": "p1", "tl_reader": "p2"}
    assert (seen["dir"] / "0001_init.sql").exists()
