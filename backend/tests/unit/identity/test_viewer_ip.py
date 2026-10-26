"""Viewer IP for the sign-in counters (SEC-6, arch 07 §7.1): `CloudFront-Viewer-Address` is `ip:port` or
`[v6]:port`; the port is dropped; IPv4 counts per address (/32), IPv6 per /64."""

from __future__ import annotations

import pytest

from tasklane.identity.viewer_ip import BadViewerAddress, viewer_ip_key


@pytest.mark.parametrize(
    ("header", "key"),
    [
        ("203.0.113.5:443", "203.0.113.5/32"),
        ("198.51.100.17:61234", "198.51.100.17/32"),
        ("[2001:db8:1:2:3:4:5:6]:5000", "2001:db8:1:2::/64"),
        ("[2001:db8:1:2:ffff::1]:443", "2001:db8:1:2::/64"),  # same /64 → same key
        ("[::ffff:203.0.113.5]:443", "203.0.113.5/32"),  # v4-mapped v6 counts as the v4 address
    ],
)
def test_real_header_samples(header: str, key: str) -> None:
    assert viewer_ip_key(header) == key


@pytest.mark.parametrize(
    "header", [None, "", "not-an-ip:443", "203.0.113.5", "[2001:db8::1]", "1.2.3.4:99999x"]
)
def test_missing_or_malformed_is_refused(header: str | None) -> None:
    with pytest.raises(BadViewerAddress):
        viewer_ip_key(header)
