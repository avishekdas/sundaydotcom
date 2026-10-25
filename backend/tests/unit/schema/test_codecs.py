"""Column codecs for the skeleton types (arch 03 §3.4; C40.6 contract rows for text, numbers, status)."""

from __future__ import annotations

import pytest

from tasklane.schema.types import CodecError, codec_for


def test_text_normalizes_and_empty_means_absent() -> None:
    c = codec_for("text")
    assert c.normalize("  hello ", {}) == "hello"
    assert c.normalize("", {}) is None and c.normalize(None, {}) is None
    with pytest.raises(CodecError):
        c.normalize("x" * 2001, {})
    with pytest.raises(CodecError):
        c.normalize(5, {})


def test_numbers_are_decimal_strings() -> None:
    c = codec_for("numbers")
    assert c.normalize("1,234.50", {}) == "1234.50"
    assert c.normalize(12, {}) == "12"
    assert c.normalize(" ", {}) is None
    for bad in ("abc", "1e400", "NaN", "Infinity", True):
        with pytest.raises(CodecError):
            c.normalize(bad, {})
    assert c.display_text("1234.50", {}) == "1234.50"


def test_status_accepts_known_label_ids_only() -> None:
    c = codec_for("status")
    settings = {"labels": [{"id": 0, "text": "Working on it"}, {"id": 1, "text": "Done"}]}
    assert c.normalize({"l": 1}, settings) == {"l": 1}
    assert c.normalize(None, settings) is None
    with pytest.raises(CodecError):
        c.normalize({"l": 7}, settings)
    with pytest.raises(CodecError):
        c.normalize("Done", settings)
    assert c.display_text({"l": 1}, settings) == "Done"


def test_unknown_type_is_rejected() -> None:
    with pytest.raises(CodecError):
        codec_for("hologram")
