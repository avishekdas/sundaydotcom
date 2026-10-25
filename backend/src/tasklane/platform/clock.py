"""Clock port (arch 10 §10.5). Business rules never call datetime.now() directly."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Deterministic clock for tests and the dev/staging fake-clock endpoint (never deployed to prod)."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware datetime")
        self._now = instant.astimezone(UTC)

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)


def local_date(instant: datetime, tz: str) -> date:
    """Calendar date of an instant in an IANA timezone (C8.3 viewer tz, C8.4/D-017 account tz)."""
    return instant.astimezone(ZoneInfo(tz)).date()


def local_minute(instant: datetime, tz: str) -> tuple[date, int, int]:
    """(local date, hour, minute) — used by T4 time triggers at local wall-clock time (06 §6.4)."""
    local = instant.astimezone(ZoneInfo(tz))
    return local.date(), local.hour, local.minute
