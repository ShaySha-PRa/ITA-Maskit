"""Unified detection record. Sensitive originals must not be written to audit.log."""

from __future__ import annotations

from dataclasses import dataclass

HIGH_MIN = 0.90
MEDIUM_MIN = 0.60


def confidence_band(score: float) -> str:
    """Map 0–1 confidence to HIGH / MEDIUM / LOW."""
    if score >= HIGH_MIN:
        return "HIGH"
    if score >= MEDIUM_MIN:
        return "MEDIUM"
    return "LOW"


@dataclass(frozen=True)
class DetectionResult:
    """One entity mention. start/end are Unicode offsets in the scanned string."""

    entity_type: str
    original_value: str
    normalized_value: str
    confidence: float
    recognizer: str
    reason: str
    source: str
    start: int | None = None
    end: int | None = None
    band: str = ""
    column: str | None = None
    sheet: str | None = None
    page: int | None = None
    rule_version: str | None = None
    subtype: str = ""
    validation_status: str = "UNKNOWN"
    evidence: str = ""
    scope: str = ""
    decision: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of range: {self.confidence}")
        if not self.band:
            object.__setattr__(self, "band", confidence_band(self.confidence))

    def span(self, text_len: int) -> tuple[int, int]:
        """Half-open interval; whole-cell hits cover the entire value."""
        if self.start is None or self.end is None:
            return 0, text_len
        return self.start, self.end
