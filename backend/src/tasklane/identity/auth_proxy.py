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

from tasklane.identity.auth_backend import (
    AuthBackend,
    BadCode,
    BadCredentials,
    InvalidRefresh,
    InviteExpired,
    Locked,
    NewPasswordRequired,
    Tokens,
    WeakPassword,
)
from tasklane.platform.clock import Clock
from tasklane.platform.counters import Counters

WINDOW_S = 15 * 60
PAIR_LIMIT = 5
ACCOUNT_LIMIT = 10
WAIT_BUDGET_S = 20.0
LOCK_MARGIN_S = 0.5
MAX_RETRIES = 2
REFRESH_LIMIT, REFRESH_WINDOW_S = 60, 60
FORGOT_PER_EMAIL, FORGOT_PER_IP, RESET_PER_IP, HOUR_S = 3, 10, 10, 3600
CHALLENGE_PER_IP = 20  # SEC-5
GENERIC = "Email or password is incorrect"


@dataclass
class AuthRefused(Exception):
    code: str  # unauthenticated | rate_limited | validation_error | invite_expired
    message: str
    retry_after_s: int | None = None
    fields: dict[str, str] | None = None


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
        self.on_reset: Callable[[str], None] | None = None

    @property
    def backend(self) -> AuthBackend:
        return self._b

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
            except NewPasswordRequired:
                # a correct temporary password: no failure counted; the caller must set a new password (F1.2)
                self._k.clear(pair)
                raise
            except InviteExpired:
                raise AuthRefused(
                    "invite_expired", "This invitation has expired. Ask an admin to send it again."
                ) from None
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

    def _per_ip(self, key: str, limit: int) -> None:
        if self._k.hit(key, HOUR_S) > limit:
            raise AuthRefused("rate_limited", "Too many requests", self._k.remaining_s(key))

    def forgot(self, email: str, ip: str) -> None:
        """Always "accepted" (SEC-5): over the per-email limit nothing is sent, but the caller cannot tell."""
        self._per_ip(f"forgot#ip#{ip}", FORGOT_PER_IP)
        email = email.strip().lower()
        if self._k.hit(f"forgot#{email}", HOUR_S) > FORGOT_PER_EMAIL:
            return
        self._b.forgot(email)

    def reset(
        self,
        email: str,
        code: str,
        new_password: str,
        ip: str,
        *,
        on_reset: Callable[[str], None] | None = None,
    ) -> None:
        """K7.3: set the new password with the emailed code, then revoke every session (AC-K7-3)."""
        self._per_ip(f"reset#ip#{ip}", RESET_PER_IP)
        email = email.strip().lower()
        try:
            self._b.confirm_reset(email, code, new_password)
        except BadCode:
            raise AuthRefused(
                "validation_error", "Invalid request", fields={"code": "Invalid or expired code"}
            ) from None
        except WeakPassword as e:
            msg = str(e) or "Password does not meet the policy"
            raise AuthRefused("validation_error", "Invalid request", fields={"new_password": msg}) from None
        self._b.global_sign_out(email)
        _, account = self._keys(email, "")
        self._k.clear(account)  # a successful reset reopens sign-in closed by D-044
        hook = on_reset or self.on_reset
        if hook:
            hook(email)

    def complete_new_password(self, email: str, session: str, new_password: str, ip: str) -> Tokens:
        """Invite acceptance (F1.2): set the first password with the session of the NEW_PASSWORD_REQUIRED step."""
        self._per_ip(f"challenge#ip#{ip}", CHALLENGE_PER_IP)
        try:
            return self._b.complete_new_password(email.strip().lower(), session, new_password)
        except WeakPassword as e:
            msg = str(e) or "Password does not meet the policy"
            raise AuthRefused("validation_error", "Invalid request", fields={"new_password": msg}) from None
        except BadCredentials:
            raise AuthRefused("unauthenticated", "This step has expired; sign in again") from None
