"""Classify a PDF page as digital-native (text layer) vs scan (image-only)."""

from __future__ import annotations

# Calibrated on synthetic fixtures: selectable sentences vs empty extract_text.
MIN_DIGITAL_CHARS = 8

KIND_DIGITAL = "digital"
KIND_SCAN = "scan"


def compact_text_len(text: str | None) -> int:
    return len("".join((text or "").split()))


def page_kind(text: str | None, *, min_chars: int = MIN_DIGITAL_CHARS) -> str:
    """Return 'digital' if the text layer has enough glyphs, else 'scan'."""
    if compact_text_len(text) >= min_chars:
        return KIND_DIGITAL
    return KIND_SCAN
