"""Auth proxy sign-in rules (ADR-013, arch 07 §7.1, S-2b): per (email, viewer IP) and per-account counters in front
of Cognito, the D-043 retry contract, the D-044 interim account closure and SEC-5 generic errors.

The fake backend models what S-2b measured: Cognito counts failures per user only, locks for 2^(n-5) s after the
n-th evaluated failure (n ≥ 5), refuses every attempt during a lock without counting it, and resets on success.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tasklane.identity.auth_backend import FakeAuthBackend
from tasklane.identity.auth_proxy import AuthProxy, AuthRefused
from tasklane.platform.clock import FakeClock
from tasklane.platform.counters import InMemoryCounters

GOOD = "Correct-Horse-Battery-9"
A, B, C = "203.0.113.1/32", "198.51.100.2/32", "192.0.2.3/32"


@pytest.fixture
def world() -> tuple[AuthProxy, FakeAuthBackend, FakeClock, list[str]]:
    clock = FakeClock(datetime(2026, 10, 26, 12, tzinfo=UTC))
    backend = FakeAuthBackend(clock)
    backend.add_user("raj@example.com", GOOD)
    events: list[str] = []
    proxy = AuthProxy(
        backend, InMemoryCounters(clock), clock, sleep=lambda s: clock.advance(seconds=s), log=events.append
    )
    return proxy, backend, clock, events


def _refused(proxy: AuthProxy, email: str, password: str, ip: str) -> AuthRefused:
    with pytest.raises(AuthRefused) as e:
        proxy.sign_in(email, password, ip)
    return e.value


def test_correct_password_returns_tokens(world) -> None:  # type: ignore[no-untyped-def]
    proxy, *_ = world
    t = proxy.sign_in("Raj@Example.com ", GOOD, A)
    assert t.access_token and t.refresh_token and t.expires_in > 0


@pytest.mark.ac("AC-K7-2")
def test_ip_a_blocked_after_five_while_ip_b_succeeds(world) -> None:  # type: ignore[no-untyped-def]
    proxy, backend, clock, _ = world
    for _ in range(5):
        assert _refused(proxy, "raj@example.com", "wrong-password-1", A).code == "unauthenticated"
    calls = backend.calls
    sixth = _refused(proxy, "raj@example.com", GOOD, A)  # refused regardless of correctness
    assert sixth.code == "rate_limited" and sixth.retry_after_s and sixth.retry_after_s <= 15 * 60
    assert backend.calls == calls  # Cognito not touched, so its own counter stays at 5
    start = clock.now()
    assert proxy.sign_in("raj@example.com", GOOD, B).access_token  # waits out Cognito's 1 s lock in-request
    assert (clock.now() - start).total_seconds() <= 35  # D-022 tolerance


def test_ip_a_block_expires_after_the_window(world) -> None:  # type: ignore[no-untyped-def]
    proxy, _, clock, _ = world
    for _ in range(5):
        _refused(proxy, "raj@example.com", "wrong-password-1", A)
    clock.advance(minutes=15, seconds=1)
    assert proxy.sign_in("raj@example.com", GOOD, A).access_token


def test_unknown_email_looks_exactly_like_a_wrong_password(world) -> None:  # type: ignore[no-untyped-def]
    proxy, *_ = world
    known = [vars(_refused(proxy, "raj@example.com", "nope-nope-nope", A)) for _ in range(6)]
    unknown = [vars(_refused(proxy, "ghost@example.com", "nope-nope-nope", A)) for _ in range(6)]
    assert known == unknown  # same codes, messages and retry_after_s sequence (SEC-5, D-043)


def test_lock_within_the_budget_is_waited_out_in_request(world) -> None:  # type: ignore[no-untyped-def]
    """D-043: wait in-request while lock + 0.5 s fits in 20 s (≤ 2 retries)."""
    proxy, _, clock, _ = world
    failures = [A] * 5 + [
        B
    ] * 4  # 9 evaluated failures (10 would close the account, D-044): lock = 2^(9-5) = 16 s
    for i, ip in enumerate(failures):
        _refused(proxy, "raj@example.com", "wrong-password-1", ip)
        if i < len(failures) - 1:
            clock.advance(seconds=40)  # let each lock expire so every failure is evaluated
    start = clock.now()
    assert proxy.sign_in("raj@example.com", GOOD, C).access_token
    assert 16 <= (clock.now() - start).total_seconds() <= 20


def test_lock_that_outlasts_the_budget_returns_retry_after(world) -> None:  # type: ignore[no-untyped-def]
    """S-2b run 8 anomaly: a lock longer than the schedule → after the budget a generic 401 with retry_after_s."""
    proxy, backend, _, _ = world
    backend.lock("raj@example.com", seconds=120)
    refused = _refused(proxy, "raj@example.com", GOOD, C)
    assert refused.code == "unauthenticated" and refused.retry_after_s


def test_d044_ten_failures_close_the_account_for_every_ip(world) -> None:  # type: ignore[no-untyped-def]
    proxy, _, clock, events = world
    for ip in (A, B):
        for _ in range(5):
            _refused(proxy, "raj@example.com", "wrong-password-1", ip)
            clock.advance(seconds=40)
    assert "auth.account_closed" in events  # Sev2 alert source
    closed = _refused(proxy, "raj@example.com", GOOD, C)
    assert closed.code == "rate_limited" and closed.retry_after_s
    clock.advance(minutes=16)
    assert proxy.sign_in("raj@example.com", GOOD, C).access_token


def test_success_resets_the_counters(world) -> None:  # type: ignore[no-untyped-def]
    proxy, *_ = world
    for _ in range(4):
        _refused(proxy, "raj@example.com", "wrong-password-1", A)
    proxy.sign_in("raj@example.com", GOOD, A)
    for _ in range(4):
        _refused(proxy, "raj@example.com", "wrong-password-1", A)
    assert proxy.sign_in("raj@example.com", GOOD, A).access_token


def test_refresh_sign_out_and_everywhere(world) -> None:  # type: ignore[no-untyped-def]
    proxy, *_ = world
    t1 = proxy.sign_in("raj@example.com", GOOD, A)
    t2 = proxy.sign_in("raj@example.com", GOOD, B)
    assert t1.refresh_token and t2.refresh_token
    assert proxy.refresh(t1.refresh_token, A).access_token
    proxy.sign_out(t1.refresh_token)  # this browser only (D-052)
    assert _refused_refresh(proxy, t1.refresh_token).code == "unauthenticated"
    assert proxy.refresh(t2.refresh_token, B).access_token
    proxy.sign_out_everywhere("raj@example.com")
    assert _refused_refresh(proxy, t2.refresh_token).code == "unauthenticated"


def test_refresh_is_rate_limited_per_ip(world) -> None:  # type: ignore[no-untyped-def]
    proxy, *_ = world
    t = proxy.sign_in("raj@example.com", GOOD, A)
    assert t.refresh_token
    for _ in range(60):
        proxy.refresh(t.refresh_token, A)
    with pytest.raises(AuthRefused) as e:
        proxy.refresh(t.refresh_token, A)
    assert e.value.code == "rate_limited"


def _refused_refresh(proxy: AuthProxy, token: str) -> AuthRefused:
    with pytest.raises(AuthRefused) as e:
        proxy.refresh(token, C)
    return e.value
