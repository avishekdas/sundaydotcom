from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def pg_uri() -> Iterator[str]:
    """Embedded PostgreSQL 18 for integration tests; TL_TEST_PG_URI overrides (CI uses a container)."""
    uri = os.environ.get("TL_TEST_PG_URI")
    if uri:
        yield uri
        return
    import embedded_postgres

    server = embedded_postgres.get_server(tempfile.mkdtemp(prefix="tl-pg-"))
    try:
        yield server.get_uri()
    finally:
        server.cleanup()
