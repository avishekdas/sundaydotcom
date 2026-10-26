"""Viewer IP key for sign-in counters (SEC-6, arch 07 §7.1).

`CloudFront-Viewer-Address` is `ip:port`; for IPv6 CloudFront sends no brackets (`2001:db8::7:443`, observed on
dev), so the port is whatever follows the last colon (`[ip]:port` is accepted too). It is trusted only on requests that carry the
CloudFront origin secret (07 §7.4, D-050). Keys: IPv4 per address (/32), IPv6 per /64; v4-mapped v6 counts as v4.
"""

from __future__ import annotations

import ipaddress
import re

_V6 = re.compile(r"^\[([0-9A-Fa-f:.]+)\]:(\d{1,5})$")
_V4 = re.compile(r"^([0-9.]+):(\d{1,5})$")
_V6_BARE = re.compile(r"^([0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*):(\d{1,5})$")


class BadViewerAddress(ValueError):
    pass


def viewer_ip_key(header: str | None) -> str:
    m = _V6.match(header or "") or _V4.match(header or "") or _V6_BARE.match(header or "")
    if not m or int(m.group(2)) > 65535:
        raise BadViewerAddress("missing or malformed CloudFront-Viewer-Address")
    try:
        ip = ipaddress.ip_address(m.group(1))
    except ValueError:
        raise BadViewerAddress("malformed viewer IP") from None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address):
        return f"{ip}/32"
    return str(ipaddress.ip_network(f"{ip}/64", strict=False))
