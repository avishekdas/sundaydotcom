"""Forward-only SQL migration runner (placeholder — implemented after the red run)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    sql: str


def discover(directory: Path) -> list[Migration]:
    raise NotImplementedError


def apply_migrations(uri: str, directory: Path) -> list[str]:
    raise NotImplementedError
