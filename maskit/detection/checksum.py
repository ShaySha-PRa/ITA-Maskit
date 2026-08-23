"""Checksum recognizers: Chinese ID (GB 11643) and bank-card Luhn.

Regex still finds lookalikes. A valid checksum raises confidence to 1.0;
a failed checksum emits LOW so HITL (Phase 7) can skip auto-mask. Phase 4
masking still applies regex hits so existing fixtures stay masked.
"""

from __future__ import annotations

import re

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.patterns import DASHED_BANK_RE, SPACED_ID_RE
from maskit.detection.result import DetectionResult

_ID_BODY_RE = re.compile(r"\d{17}[\dXx]")
_BANK_DIGIT_RE = re.compile(r"\d{16,19}")

# GB 11643-1999
_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = "10X98765432"


def id_card_checksum_ok(value: str) -> bool:
    """True if 18-char id (spaces stripped) has a valid GB 11643 check digit."""
    compact = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"\d{17}[\dX]", compact):
        return False
    total = sum(int(compact[i]) * _ID_WEIGHTS[i] for i in range(17))
    return compact[17] == _ID_CHECK[total % 11]


def luhn_ok(digits: str) -> bool:
    """Luhn checksum for a digit string."""
    if not digits.isdigit() or not (16 <= len(digits) <= 19):
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


class ChecksumRecognizer(Recognizer):
    name = "checksum"

    def detect(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        hits: list[DetectionResult] = []
        id_rule = ctx.ruleset.defs.get("id_card")
        bank_rule = ctx.ruleset.defs.get("bank_card")
        if id_rule and not id_rule.default_disabled:
            hits.extend(self._id_hits(text, id_rule.version, ctx))
        if bank_rule and not bank_rule.default_disabled:
            hits.extend(self._bank_hits(text, bank_rule.version, ctx))
        return hits

    def _id_hits(self, text: str, version: str, ctx: DetectContext) -> list[DetectionResult]:
        out: list[DetectionResult] = []
        seen: set[tuple[int, int]] = set()
        for regex in (_ID_BODY_RE, SPACED_ID_RE):
            for m in regex.finditer(text):
                span = (m.start(), m.end())
                if span in seen:
                    continue
                seen.add(span)
                raw = m.group(0)
                compact = re.sub(r"\s+", "", raw)
                ok = id_card_checksum_ok(compact)
                out.append(
                    DetectionResult(
                        entity_type="id_card",
                        original_value=raw,
                        normalized_value=compact.upper(),
                        confidence=1.0 if ok else 0.45,
                        recognizer=self.name,
                        reason="GB 11643 checksum ok" if ok else "GB 11643 checksum failed",
                        source=ctx.source,
                        start=m.start(),
                        end=m.end(),
                        column=ctx.column,
                        sheet=ctx.sheet,
                        page=ctx.page,
                        rule_version=version,
                        validation_status="VALID" if ok else "INVALID",
                        evidence="checksum",
                    )
                )
        return out

    def _bank_hits(self, text: str, version: str, ctx: DetectContext) -> list[DetectionResult]:
        out: list[DetectionResult] = []
        seen: set[tuple[int, int]] = set()
        for regex in (_BANK_DIGIT_RE, DASHED_BANK_RE):
            for m in regex.finditer(text):
                span = (m.start(), m.end())
                if span in seen:
                    continue
                digits = re.sub(r"[\s\-]", "", m.group(0))
                if not (16 <= len(digits) <= 19):
                    continue
                seen.add(span)
                ok = luhn_ok(digits)
                out.append(
                    DetectionResult(
                        entity_type="bank_card",
                        original_value=m.group(0),
                        normalized_value=digits,
                        confidence=1.0 if ok else 0.45,
                        recognizer=self.name,
                        reason="Luhn checksum ok" if ok else "Luhn checksum failed",
                        source=ctx.source,
                        start=m.start(),
                        end=m.end(),
                        column=ctx.column,
                        sheet=ctx.sheet,
                        page=ctx.page,
                        rule_version=version,
                        validation_status="VALID" if ok else "INVALID",
                        evidence="checksum",
                    )
                )
        return out


def annotate_with_checksum(result: DetectionResult) -> DetectionResult:
    """Return a copy with checksum-adjusted confidence for id/bank cards."""
    if result.entity_type == "id_card":
        ok = id_card_checksum_ok(result.normalized_value)
    elif result.entity_type == "bank_card":
        ok = luhn_ok(re.sub(r"[\s\-]", "", result.normalized_value))
    else:
        return result
    conf = 1.0 if ok else min(result.confidence, 0.45)
    reason = result.reason
    if ok and result.confidence < 1.0:
        reason = f"{result.reason}; checksum ok"
    elif not ok:
        reason = f"{result.reason}; checksum failed"
    return DetectionResult(
        entity_type=result.entity_type,
        original_value=result.original_value,
        normalized_value=result.normalized_value,
        confidence=conf,
        recognizer=result.recognizer,
        reason=reason,
        source=result.source,
        start=result.start,
        end=result.end,
        column=result.column,
        sheet=result.sheet,
        page=result.page,
        rule_version=result.rule_version,
        subtype=result.subtype,
        validation_status="VALID" if ok else "INVALID",
        evidence="checksum",
        scope=result.scope,
        decision=result.decision,
    )
