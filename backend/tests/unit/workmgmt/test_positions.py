"""Fractional-index positions (arch 03 §3.1): a move rewrites one row; keys sort with COLLATE "C"."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tasklane.workmgmt.positions import key_between

KEY = st.text(
    alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", min_size=1, max_size=6
).filter(lambda k: not k.endswith("0"))


def test_examples() -> None:
    assert "a" < key_between("a", "b") < "b"
    assert key_between(None, "a") < "a"
    assert key_between("a", None) > "a"
    assert key_between(None, None)


@given(KEY, KEY)
def test_strictly_between(a: str, b: str) -> None:
    lo, hi = sorted((a, b))
    if lo == hi:
        return
    k = key_between(lo, hi)
    assert lo < k < hi and not k.endswith("0")


@given(KEY)
def test_open_ends(a: str) -> None:
    assert key_between(None, a) < a < key_between(a, None)
