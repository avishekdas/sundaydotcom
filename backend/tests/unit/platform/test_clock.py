"""Clock port (arch 10 §10.5): fakeable time for T4/DST, nightly jobs and timezone rules (C8, D-017)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from tasklane.platform.clock import FakeClock, SystemClock, local_date, local_minute


def test_system_clock_is_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None and now.utcoffset() == timedelta(0)


def test_fake_clock_advances() -> None:
    c = FakeClock(datetime(2026, 10, 25, 12, 0, tzinfo=UTC))
    c.advance(minutes=90)
    assert c.now() == datetime(2026, 10, 25, 13, 30, tzinfo=UTC)


def test_fake_clock_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="aware"):
        FakeClock(datetime(2026, 1, 1))


@pytest.mark.ac_partial("AC-C8-3")  # helper only; the AC is owned by M2 (M0B-29)
def test_local_date_uses_the_given_timezone() -> None:
    # 2026-10-25T20:00Z is already 26 Oct in Kolkata (UTC+5:30), still 25 Oct in New York
    instant = datetime(2026, 10, 25, 20, 0, tzinfo=UTC)
    assert local_date(instant, "Asia/Kolkata") == date(2026, 10, 26)
    assert local_date(instant, "America/New_York") == date(2026, 10, 25)


@pytest.mark.ac_partial("AC-C8-2")  # helper only; the AC is owned by M5 (M0B-29)
def test_local_minute_follows_dst() -> None:
    # 09:00 New York is 13:00Z before the DST change (1 Nov 2026) and 14:00Z after it
    assert local_minute(datetime(2026, 10, 30, 13, 0, tzinfo=UTC), "America/New_York") == (
        date(2026, 10, 30),
        9,
        0,
    )
    assert local_minute(datetime(2026, 11, 2, 14, 0, tzinfo=UTC), "America/New_York") == (
        date(2026, 11, 2),
        9,
        0,
    )
