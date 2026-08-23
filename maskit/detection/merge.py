"""Overlap resolution by evidence strength, not registration order."""

from __future__ import annotations

from maskit.detection.result import DetectionResult

_EVIDENCE_RANK = {
    "validated": 50,
    "column+validator": 45,
    "column+prefix": 44,
    "context": 40,
    "prefix": 38,
    "column": 30,
    "person-list span": 28,
    "person-list exact": 28,
    "name gazetteer": 26,
    "semantic prefix name": 24,
    "semantic prefix/gazetteer company": 24,
    "surname heuristic (no list)": 18,
    "regex search": 12,
    "regex fullmatch": 12,
    "checksum": 10,
}

_TYPE_RANK = {
    "email": 80,
    "ip": 78,
    "id_card": 76,
    "bank_card": 74,
    "phone": 72,
    "name": 40,
    "company": 38,
    "employee_id": 20,
    "app_version": 15,
}

_VALID_RANK = {"VALID": 2, "UNKNOWN": 1, "INVALID": 0}

REASON_WHOLE_CELL = "whole_cell_winner"
REASON_OUTRANKS = "outranks"


class ConflictResolver:
    """Keep non-overlapping detections. Whole-cell hits suppress spans."""

    def __init__(self) -> None:
        self.last_trace: list[dict] = []

    def merge(self, results: list[DetectionResult], text_len: int = 0) -> list[DetectionResult]:
        self.last_trace = []
        if not results:
            return []
        whole = [r for r in results if r.start is None or r.end is None]
        if whole:
            whole.sort(key=self._key, reverse=True)
            winner = whole[0]
            self.last_trace.append(
                {
                    "winner": winner.entity_type,
                    "reason_code": REASON_WHOLE_CELL,
                    "suppressed": [
                        {
                            "entity_type": r.entity_type,
                            "reason": "whole-cell winner",
                            "reason_code": REASON_WHOLE_CELL,
                        }
                        for r in whole[1:]
                    ],
                }
            )
            return [winner]

        n = text_len or max((r.end or 0) for r in results)
        ranked = sorted(results, key=self._key, reverse=True)
        kept: list[DetectionResult] = []
        occupied: list[tuple[int, int]] = []
        for r in ranked:
            a, b = r.span(n)
            conflict = next((k for k, (s, e) in enumerate(occupied) if a < e and s < b), None)
            if conflict is not None:
                winner = kept[conflict]
                self.last_trace.append(
                    {
                        "winner": winner.entity_type,
                        "reason_code": REASON_OUTRANKS,
                        "suppressed": [
                            {
                                "entity_type": r.entity_type,
                                "reason": (
                                    f"{winner.evidence or winner.recognizer} "
                                    f"{winner.entity_type} outranks "
                                    f"{r.evidence or r.recognizer} {r.entity_type}"
                                ),
                                "reason_code": REASON_OUTRANKS,
                            }
                        ],
                    }
                )
                continue
            kept.append(r)
            occupied.append((a, b))
        kept.sort(key=lambda r: (-len(r.original_value), r.start or 0))
        return kept

    def _key(self, r: DetectionResult) -> tuple:
        length = len(r.original_value)
        evid = _EVIDENCE_RANK.get(r.evidence, 5)
        if r.evidence not in _EVIDENCE_RANK and r.reason:
            for prefix, rank in (
                ("regex", 12),
                ("column", 30),
                ("GB 11643 checksum ok", 55),
                ("Luhn checksum ok", 55),
            ):
                if r.reason.startswith(prefix) or prefix in r.reason:
                    evid = max(evid, rank)
                    break
            if "checksum ok" in r.reason:
                evid = max(evid, 55)
        valid = _VALID_RANK.get(r.validation_status, 1)
        type_rank = _TYPE_RANK.get(r.entity_type, 10)
        return (length, valid, evid, r.confidence, type_rank)
