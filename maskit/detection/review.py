"""Review manifest: no raw PII by default."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from maskit.detection.result import DetectionResult


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def redacted_preview(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "***" + value[-1:]


def hit_to_manifest(
    hit: DetectionResult,
    *,
    file: str,
    fmt: str,
    include_value: bool = False,
) -> dict:
    row = {
        "file": file,
        "format": fmt,
        "sheet": hit.sheet,
        "column": hit.column,
        "page": hit.page,
        "start": hit.start,
        "end": hit.end,
        "entity_type": hit.entity_type,
        "subtype": hit.subtype,
        "detection_score": hit.confidence,
        "validation_status": hit.validation_status,
        "recognizer": hit.recognizer,
        "evidence": hit.evidence,
        "decision": hit.decision,
        "reason": hit.reason,
        "fingerprint": fingerprint(hit.original_value),
        "preview": redacted_preview(hit.original_value),
        "rule_version": hit.rule_version,
    }
    if include_value:
        row["original_value"] = hit.original_value
    return row


def write_review_manifest(path: str | Path, rows: list[dict]) -> None:
    p = Path(path)
    p.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


class UnresolvedReviewError(ValueError):
    """strict policy: REVIEW hits remain; do not write a success output."""


def load_review_manifest(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def row_exposes_raw_value(row: dict) -> bool:
    return bool(row.get("original_value"))
