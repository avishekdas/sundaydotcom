"""M0B-14: role passwords travel as SCRAM-SHA-256 verifiers, never as plaintext SQL (RFC 5802 / 7677)."""

from __future__ import annotations

import base64
import hashlib
import hmac

from tasklane.platform.migrations import role_password_sql, scram_verifier


def test_verifier_format_and_derivation() -> None:
    salt = bytes(range(16))
    v = scram_verifier("pencil", salt=salt, iterations=4096)
    head, keys = v.split("$", 2)[0:2], v.split("$")[2]
    assert head == ["SCRAM-SHA-256", f"4096:{base64.b64encode(salt).decode()}"]
    stored_b64, server_b64 = keys.split(":")
    salted = hashlib.pbkdf2_hmac("sha256", b"pencil", salt, 4096)
    client_key = hmac.new(salted, b"Client Key", "sha256").digest()
    assert base64.b64decode(stored_b64) == hashlib.sha256(client_key).digest()
    assert base64.b64decode(server_b64) == hmac.new(salted, b"Server Key", "sha256").digest()


def test_password_sql_never_contains_the_plaintext() -> None:
    sql = role_password_sql("tl_api_rw", "Sup3r-Secret-Value")
    assert "Sup3r-Secret-Value" not in sql
    assert sql.startswith('alter role "tl_api_rw" login password \'SCRAM-SHA-256$4096:')


def test_random_salt_per_call() -> None:
    assert scram_verifier("x") != scram_verifier("x")
