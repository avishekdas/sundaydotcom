"""Auth proxy rules (ADR-013, arch 07 §7.1, S-2b, D-043, D-044, SEC-5).

- Per (email, viewer IP): 5 failures in 15 min → that IP is refused for that account (`rate_limited`) without
  calling Cognito, so one IP never drives Cognito's per-user lock past its first step (AC-K7-2).
- Per account: 10 failures in 15 min from any IPs → sign-in closed for the rest of the window (D-044, until CAPTCHA
  in M6); emits `auth.account_closed` (Sev2). Password reset stays available.
- Cognito lock (D-043): wait in-request while the expected lock (2^(n-5) s from our own account counter) + 0.5 s fits
  in a 20 s budget, ≤ 2 retries; otherwise a generic 401 with `retry_after_s`.
- Every failure is the same generic 401; `retry_after_s` comes from our counters only, so unknown emails look the same.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from tasklane.identity.auth_backend import AuthBackend, BadCredentials, InvalidRefresh, Locked, Tokens
from tasklane.platform.clock import Clock
from tasklane.platform.counters import Counters

WINDOW_S = 15 * 60
PAIR_LIMIT = 5
ACCOUNT_LIMIT = 10
WAIT_BUDGET_S = 20.0
LOCK_MARGIN_S = 0.5
MAX_RETRIES = 2
REFRESH_LIMIT, REFRESH_WINDOW_S = 60, 60
GENERIC = "Email or password is incorrect"


@dataclass
class AuthRefused(Exception):
    code: str  # unauthenticated | rate_limited
    message: str
    retry_after_s: int | None = None


def _metric(name: str) -> None:
    print(json.dumps({"metric": name}))


class AuthProxy:
    def __init__(
        self,
        backend: AuthBackend,
        counters: Counters,
        clock: Clock,
        *,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = _metric,
    ) -> None:
        self._b, self._k, self._clock, self._sleep, self._log = backend, counters, clock, sleep, log

    @staticmethod
    def _keys(email: str, ip: str) -> tuple[str, str]:
        return f"signin#{email}#{ip}", f"signin#{email}"

    def _expected_lock(self, account: str) -> float:
        n = self._k.count(account)
        return float(2 ** (n - 5)) if n >= 5 else 0.0

    def sign_in(self, email: str, password: str, ip: str) -> Tokens:
        email = email.strip().lower()
        pair, account = self._keys(email, ip)
        for key, limit in ((pair, PAIR_LIMIT), (account, ACCOUNT_LIMIT)):
            if self._k.count(key) >= limit:
                raise AuthRefused(
                    "rate_limited", "Too many attempts; try again later", self._k.remaining_s(key)
                )
        waited = 0.0
        for attempt in range(MAX_RETRIES + 1):
            try:
                tokens = self._b.sign_in(email, password)
            except BadCredentials:
                self._k.hit(pair, WINDOW_S)
                if self._k.hit(account, WINDOW_S) == ACCOUNT_LIMIT:
                    self._log("auth.account_closed")
                lock = self._expected_lock(account)
                raise AuthRefused("unauthenticated", GENERIC, math.ceil(lock) if lock else None) from None
            except Locked:
                wait = self._expected_lock(account) + LOCK_MARGIN_S
                if attempt < MAX_RETRIES and waited + wait <= WAIT_BUDGET_S:
                    self._sleep(wait)
                    waited += wait
                    continue
                raise AuthRefused("unauthenticated", GENERIC, math.ceil(wait)) from None
            self._k.clear(pair)
            self._k.clear(account)
            return tokens
        raise AssertionError("unreachable")  # pragma: no cover

    def refresh(self, refresh_token: str, ip: str) -> Tokens:
        key = f"refresh#{ip}"
        if self._k.hit(key, REFRESH_WINDOW_S) > REFRESH_LIMIT:
            raise AuthRefused("rate_limited", "Too many requests", self._k.remaining_s(key))
        try:
            return self._b.refresh(refresh_token)
        except InvalidRefresh:
            raise AuthRefused("unauthenticated", "Session expired; sign in again") from None

    def sign_out(self, refresh_token: str) -> None:
        """This browser only (D-052); a failed revoke still clears the cookie."""
        try:
            self._b.revoke(refresh_token)
        except Exception as e:
            print(json.dumps({"metric": "auth.revoke_error", "error": type(e).__name__}))

    def sign_out_everywhere(self, email: str) -> None:
        self._b.global_sign_out(email)
