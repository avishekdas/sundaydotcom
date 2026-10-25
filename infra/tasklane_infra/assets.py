"""Lambda code assets built from the backend checkout (pure Python; boto3 comes from the runtime)."""

from __future__ import annotations

import shutil
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "infra" / ".build"


@cache
def backend_asset() -> str:
    """Copy backend/src/tasklane (+ migrations as tasklane/migrations_sql) into a clean build dir."""
    out = BUILD / "backend"
    if out.exists():
        shutil.rmtree(out)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(REPO / "backend" / "src" / "tasklane", out / "tasklane", ignore=ignore)
    shutil.copytree(REPO / "backend" / "migrations", out / "tasklane" / "migrations_sql", ignore=ignore)
    return str(out)
