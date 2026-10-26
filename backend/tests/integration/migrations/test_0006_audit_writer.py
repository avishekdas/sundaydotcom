"""0006: the audit store is append-only through its own role (arch 07 §7.3, D-056)."""

from __future__ import annotations

import psycopg
import pytest
from psycopg import errors

pytestmark = pytest.mark.integration


def test_only_audit_writer_appends(fresh_db: str) -> None:
    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute("set role tl_audit_writer")
        c.execute("insert into tl.audit_events (kind, target, ip) values ('sign_in', '{}', '203.0.113.5/32')")
        for sql in (
            "update tl.audit_events set kind = 'x'",
            "delete from tl.audit_events",
            "select * from tl.audit_events",
            "select * from tl.users",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                c.execute(sql)
    with psycopg.connect(fresh_db, autocommit=True) as c:
        c.execute("set role tl_api_rw")
        with pytest.raises(errors.InsufficientPrivilege):
            c.execute("insert into tl.audit_events (kind) values ('forged')")
