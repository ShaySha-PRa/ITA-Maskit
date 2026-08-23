"""Unified phone recognition for document, table, OCR, preview, execute."""

from __future__ import annotations

import re
import unicodedata

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.result import DetectionResult
from maskit.detection.scope import ValidationStatus

_CC = r"(?:\+?86|0086)"
_MOBILE_FLEX = r"1[3-9]\d(?:[\s\-]?\d){8}"
_LAND_FLEX = r"0\d{2,3}[\s\-]\d{7,8}(?:[\s\-]\d{1,6})?"

MOBILE_RE = re.compile(rf"(?<!\d)(?:{_CC}[\s\-]?)?{_MOBILE_FLEX}(?!\d)")
LANDLINE_RE = re.compile(rf"(?<!\d)(?:{_CC}[\s\-]?)?{_LAND_FLEX}(?!\d)")
DATE_RE = re.compile(r"^(?:19|20)\d{2}[./\-]\d{1,2}(?:[./\-]\d{1,2})?$")
MOBILE_CANON_RE = re.compile(r"^1[3-9]\d{9}$")
LAND_COMPACT_RE = re.compile(r"^0\d{9,11}$")


def nfkc_half(text: str) -> str:
    if not text or text.isascii():
        return text
    return unicodedata.normalize("NFKC", text)


def is_date_like(value: str) -> bool:
    return DATE_RE.fullmatch(nfkc_half(value).strip()) is not None


def canonical_phone(value: str) -> str:
    """Drop separators; map 0086/86 → +86."""
    chars = []
    for ch in nfkc_half(value):
        if ch.isdigit() or ch == "+":
            chars.append(ch)
    d = "".join(chars)
    if d.startswith("+0086"):
        d = "+86" + d[5:]
    elif d.startswith("0086"):
        d = "+86" + d[4:]
    elif d.startswith("+86"):
        pass
    elif d.startswith("86") and len(d) >= 13:
        d = "+86" + d[2:]
    return d


def _landline_ok(compact: str) -> bool:
    """0 + 2–3 digit area + 7–8 local = 10–12 digits."""
    if not LAND_COMPACT_RE.fullmatch(compact):
        return False
    # 3-digit area (010/021…): 0 + 2 + 8 local = 11; or 7 local = 10
    # 4-digit area (0755…): 0 + 3 + 7–8 local = 11–12
    return 10 <= len(compact) <= 12


def classify_phone(value: str, *, column_mode: bool = False) -> tuple[str, str] | None:
    """Return (subtype, canonical) or None. Dates are never phones."""
    s = nfkc_half(value).strip()
    if not s or is_date_like(s):
        return None
    canon = canonical_phone(s)
    body = canon.removeprefix("+86")
    if MOBILE_CANON_RE.fullmatch(body):
        return "mobile", canon
    compact = re.sub(r"\D", "", body)
    has_sep = bool(re.search(r"[\s\-]", s))
    if _landline_ok(compact) and compact.startswith("0") and (column_mode or has_sep):
        return "landline", compact
    return None


def is_phone_value(value: str, *, column_mode: bool = False) -> bool:
    s = value.strip()
    if not s or DATE_RE.fullmatch(s):
        return False
    if column_mode and s.isascii():
        if MOBILE_CANON_RE.fullmatch(s):
            return True
        if s.startswith("0") and LAND_COMPACT_RE.fullmatch(s):
            return True
        if LANDLINE_RE.fullmatch(s):
            return True
    return classify_phone(s, column_mode=column_mode) is not None


def find_phones(text: str) -> list[tuple[int, int, str, str, str]]:
    """(start, end, original, canonical, subtype). Spans on NFKC text ≈ original for fullwidth."""
    scan = nfkc_half(text)
    found: list[tuple[int, int, str, str, str]] = []
    seen: set[tuple[int, int]] = set()
    for regex in (MOBILE_RE, LANDLINE_RE):
        for m in regex.finditer(scan):
            key = (m.start(), m.end())
            if key in seen:
                continue
            orig = text[m.start() : m.end()]
            classified = classify_phone(orig, column_mode=False)
            if classified is None:
                continue
            seen.add(key)
            subtype, canon = classified
            found.append((m.start(), m.end(), orig, canon, subtype))
    found.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    return found


def _hit(
    rule,
    orig: str,
    canon: str,
    subtype: str,
    ctx: DetectContext,
    start: int | None,
    end: int | None,
    reason: str,
    evidence: str,
    conf: float,
) -> DetectionResult:
    return DetectionResult(
        entity_type="phone",
        original_value=orig,
        normalized_value=canon,
        confidence=conf,
        recognizer="phone",
        reason=reason,
        source=ctx.source,
        start=start,
        end=end,
        column=ctx.column,
        sheet=ctx.sheet,
        page=ctx.page,
        rule_version=rule.version,
        subtype=subtype,
        validation_status=ValidationStatus.VALID.value,
        evidence=evidence,
        scope=ctx.path,
    )


class PhoneRecognizer(Recognizer):
    name = "phone"

    def detect(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        if not text:
            return []
        rule = ctx.ruleset.defs.get("phone")
        if rule is None or rule.default_disabled:
            return []
        column_mode = ctx.mapped_rule is not None and ctx.mapped_rule.name == "phone"
        if ctx.path == "structured" and not column_mode:
            return []
        if column_mode and ctx.path == "structured":
            classified = classify_phone(text, column_mode=True)
            if classified is None:
                return []
            subtype, canon = classified
            return [
                _hit(
                    rule,
                    text.strip(),
                    canon,
                    subtype,
                    ctx,
                    None,
                    None,
                    f"phone column {subtype}",
                    "column+validator",
                    0.95,
                )
            ]
        return [
            _hit(
                rule,
                orig,
                canon,
                subtype,
                ctx,
                start,
                end,
                f"phone {subtype}",
                "validated",
                0.93 if subtype == "mobile" else 0.91,
            )
            for start, end, orig, canon, subtype in find_phones(text)
        ]
