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
    # Singleton workers (outbox-sweeper, scheduler-tick). D-037: dev runs hourly 08:00-19:00 New York time so the
    # Aurora cluster can auto-pause (min 0 ACU) overnight and between runs.
    worker_schedule: str = "rate(1 minute)"
    worker_schedule_tz: str = "UTC"
    dead_man_hours: int = 0
    alert_email: str | None = None
    test_hooks: bool = False  # fake clock / fault injection endpoints; refused for prod (plan M0b-8)
    # D-039: dev has CloudTrail only; GuardDuty / Security Hub / Config come with a prod stage
    security_baseline: tuple[str, ...] = (
        "cloudtrail",
        "guardduty",
        "securityhub",
        "config",
    )  # 0 → 5-minute dead-man window; >0 → alarm after this many hours without a tick


DEV = Stage(
    name="dev",
    account="920824005451",
    region="us-east-1",
    domain=None,
    aurora_min_acu=0,
    aurora_max_acu=4,
    worker_schedule="cron(0 8-19 * * ? *)",
    worker_schedule_tz="America/New_York",
    dead_man_hours=14,  # 12 quiet hours overnight + 2 missed daytime runs
    alert_email="avishekdas.cool@gmail.com",  # D-040
    security_baseline=("cloudtrail",),
    test_hooks=True,
)
