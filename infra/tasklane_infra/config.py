"""Stage configuration (D-031: dev only for now)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    name: str
    account: str
    region: str
    domain: str | None  # None → CloudFront default domain (D-035: avishekdas.dev is not registered yet)
    aurora_min_acu: float
    aurora_max_acu: float


DEV = Stage(
    name="dev",
    account="920824005451",
    region="us-east-1",
    domain=None,
    aurora_min_acu=0,
    aurora_max_acu=4,
)
