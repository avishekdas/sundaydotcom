"""Column codecs (arch 03 §3.4): validate/normalize to the stored JSON value; ``None`` means "key absent"."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

Settings = dict[str, Any]


class CodecError(ValueError):
    """The value is invalid for the column type (→ 400 validation_error with the field)."""


class Codec(Protocol):
    type: str

    def normalize(self, raw: Any, settings: Settings) -> Any: ...
    def display_text(self, value: Any, settings: Settings) -> str: ...


class TextCodec:
    type = "text"
    MAX = 2000

    def normalize(self, raw: Any, settings: Settings) -> Any:
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise CodecError("text must be a string")
        s = raw.strip()
        if len(s) > self.MAX:
            raise CodecError(f"text is longer than {self.MAX} characters")
        return s or None

    def display_text(self, value: Any, settings: Settings) -> str:
        return str(value or "")


class NumbersCodec:
    type = "numbers"
    _CLEAN = re.compile(r"[,\s]")

    def normalize(self, raw: Any, settings: Settings) -> Any:
        if raw is None:
            return None
        if isinstance(raw, bool) or not isinstance(raw, int | str | Decimal):
            raise CodecError("numbers must be a decimal string or an integer")
        s = self._CLEAN.sub("", str(raw))
        if not s:
            return None
        try:
            d = Decimal(s)
        except InvalidOperation as e:
            raise CodecError("not a number") from e
        if not d.is_finite() or abs(d.adjusted()) > 30:
            raise CodecError("number out of range")
        return format(d, "f")

    def display_text(self, value: Any, settings: Settings) -> str:
        return str(value or "")


class StatusCodec:
    type = "status"

    def normalize(self, raw: Any, settings: Settings) -> Any:
        if raw is None:
            return None
        if (
            not isinstance(raw, dict)
            or set(raw) != {"l"}
            or isinstance(raw["l"], bool)
            or not isinstance(raw["l"], int)
        ):
            raise CodecError('status must be {"l": <label id>}')
        if raw["l"] not in {lab["id"] for lab in settings.get("labels", [])}:
            raise CodecError("unknown status label")
        return {"l": raw["l"]}

    def display_text(self, value: Any, settings: Settings) -> str:
        if not value:
            return ""
        return next((lab["text"] for lab in settings.get("labels", []) if lab["id"] == value["l"]), "")


_CODECS: dict[str, Codec] = {c.type: c for c in (TextCodec(), NumbersCodec(), StatusCodec())}


def codec_for(column_type: str) -> Codec:
    try:
        return _CODECS[column_type]
    except KeyError:
        raise CodecError(f"unsupported column type {column_type!r}") from None
