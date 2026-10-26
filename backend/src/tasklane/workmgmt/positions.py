"""Fractional-index keys (arch 03 §3.1): positions are text sorted with COLLATE "C", so a move rewrites one row.

Base-62 digits in ASCII order; keys never end in "0", so there is always room between two keys.
"""

from __future__ import annotations

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _midpoint(a: str, b: str | None) -> str:
    if b is not None:
        n = 0
        while (a[n] if n < len(a) else "0") == b[n]:
            n += 1
        if n:
            return b[:n] + _midpoint(a[n:], b[n:])
    da = DIGITS.index(a[0]) if a else 0
    db = DIGITS.index(b[0]) if b is not None else len(DIGITS)
    if db - da > 1:
        return DIGITS[(da + db) // 2]
    if b is not None and len(b) > 1:
        return b[0]
    return DIGITS[da] + _midpoint(a[1:], None)


def key_between(a: str | None, b: str | None) -> str:
    """A key strictly between ``a`` and ``b`` (``None`` = open end). Requires ``a < b`` when both are given."""
    if a is not None and b is not None and not a < b:
        raise ValueError(f"key_between needs a < b, got {a!r}, {b!r}")
    return _midpoint(a or "", b)


def spread(n: int) -> list[str]:
    """``n`` increasing keys, used to renumber a list whose keys collide."""
    keys: list[str] = []
    for _ in range(n):
        keys.append(key_between(keys[-1] if keys else None, None))
    return keys
