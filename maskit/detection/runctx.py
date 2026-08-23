"""Per-run HITL stats. No raw PII; fingerprints only."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

from maskit.detection.review import fingerprint, redacted_preview


@dataclass
class RunStats:
    auto_apply: int = 0
    review: int = 0
    reject: int = 0
    review_rows: list[dict] = field(default_factory=list)
    pdf_verify: dict | None = None

    def add_review(
        self,
        *,
        entity_type: str,
        value: str,
        file: str = "",
        fmt: str = "",
        column: str | None = None,
        sheet: str | None = None,
        page: int | None = None,
        reason: str = "",
        validation_status: str = "INVALID",
        recognizer: str = "",
        detection_score: float | None = None,
        subtype: str = "",
    ) -> None:
        self.review += 1
        self.review_rows.append(
            {
                "file": file,
                "format": fmt,
                "sheet": sheet,
                "column": column,
                "page": page,
                "entity_type": entity_type,
                "subtype": subtype,
                "detection_score": detection_score,
                "validation_status": validation_status,
                "recognizer": recognizer,
                "decision": "REVIEW",
                "reason": reason,
                "fingerprint": fingerprint(value),
                "preview": redacted_preview(value),
            }
        )


_STATS: ContextVar[RunStats | None] = ContextVar("maskit_run_stats", default=None)


def begin_run() -> RunStats:
    stats = RunStats()
    _STATS.set(stats)
    return stats


def current_run() -> RunStats:
    stats = _STATS.get()
    if stats is None:
        stats = RunStats()
        _STATS.set(stats)
    return stats
