"""Split a SQL script into single statements (the Data API runs one statement per call)."""

from __future__ import annotations

import re

_DOLLAR_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def split_statements(script: str) -> list[str]:
    """Split on top-level ``;`` — not inside '…', "…", $tag$…$tag$, -- or /* */ comments.

    Statements that are only whitespace/comments are dropped; leading comments of a real statement are kept.
    """
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(script)
    while i < n:
        ch = script[i]
        if ch == "'" or ch == '"':
            j = i + 1
            while j < n:
                if script[j] == ch:
                    if j + 1 < n and script[j + 1] == ch:  # doubled quote escape
                        j += 2
                        continue
                    break
                j += 1
            buf.append(script[i : j + 1])
            i = j + 1
        elif script.startswith("--", i):
            j = script.find("\n", i)
            j = n if j < 0 else j
            buf.append(script[i:j])
            i = j
        elif script.startswith("/*", i):
            j = script.find("*/", i + 2)
            j = n if j < 0 else j + 2
            buf.append(script[i:j])
            i = j
        elif (
            ch == "$"
            and (m := _DOLLAR_TAG.match(script, i))
            and not (i > 0 and (script[i - 1].isalnum() or script[i - 1] == "_"))
        ):
            tag = m.group(0)
            j = script.find(tag, m.end())
            j = n if j < 0 else j + len(tag)
            buf.append(script[i:j])
            i = j
        elif ch == ";":
            out.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(ch)
            i += 1
    out.append("".join(buf))
    return [s.strip() for s in out if _has_code(s)]


def _has_code(stmt: str) -> bool:
    no_line = re.sub(r"--[^\n]*", "", stmt)
    no_block = re.sub(r"/\*.*?\*/", "", no_line, flags=re.DOTALL)
    return bool(no_block.strip())
