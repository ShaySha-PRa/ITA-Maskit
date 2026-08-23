"""Employee ID: configured prefixes or explicit context. Never PREFIX-NUMBER guessing."""

from __future__ import annotations

import re

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.phone import classify_phone
from maskit.detection.result import DetectionResult
from maskit.detection.scope import DEFAULT_EMPLOYEE_PREFIXES, ValidationStatus

_CONTEXT_RE = re.compile(
    r"(?:工号|员工编号|人员编号|员工号|员工id|employee\s*id|employee\s*no|"
    r"staff\s*id|eid)\s*[：:]?\s*",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*-\d{4,}|\b[A-Za-z]\d{4,}\b")
_PREFIX_TOKEN_RE = re.compile(r"([A-Za-z][A-Za-z0-9]*)-([A-Za-z0-9]{4,})")


def _prefixes(ctx: DetectContext) -> tuple[str, ...]:
    rule = ctx.ruleset.defs.get("employee_id") if ctx.ruleset else None
    raw = getattr(rule, "prefixes", None) or DEFAULT_EMPLOYEE_PREFIXES
    return tuple(p.upper() for p in raw if p)


def looks_like_employee_id(
    value: str, prefixes: tuple[str, ...], *, column_mode: bool = False
) -> bool:
    s = value.strip()
    if not s:
        return False
    if not s[:1].isalpha() and classify_phone(s, column_mode=True):
        return False
    m = _PREFIX_TOKEN_RE.fullmatch(s)
    if not m:
        return False
    if column_mode:
        return True
    return m.group(1).upper() in prefixes


def find_employee_ids(
    text: str, prefixes: tuple[str, ...]
) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    def add(start: int, end: int, orig: str) -> None:
        if orig in seen:
            return
        if classify_phone(orig, column_mode=True):
            return
        seen.add(orig)
        hits.append((start, end, orig))

    for m in _PREFIX_TOKEN_RE.finditer(text):
        if m.group(1).upper() in prefixes:
            add(m.start(), m.end(), m.group(0))

    for cm in _CONTEXT_RE.finditer(text):
        rest = text[cm.end() :]
        tm = _TOKEN_RE.match(rest)
        if not tm:
            continue
        orig = tm.group(0)
        add(cm.end() + tm.start(), cm.end() + tm.end(), orig)
    return hits


class EmployeeIdRecognizer(Recognizer):
    name = "employee_id"

    def detect(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        if not text:
            return []
        rule = ctx.ruleset.defs.get("employee_id")
        if rule is None or rule.default_disabled:
            return []
        prefixes = _prefixes(ctx)
        column_mode = ctx.mapped_rule is not None and ctx.mapped_rule.name == "employee_id"
        if ctx.path == "structured" and not column_mode:
            return []
        if column_mode and ctx.path == "structured":
            s = text.strip()
            if not looks_like_employee_id(s, prefixes, column_mode=True):
                return []
            return [
                DetectionResult(
                    entity_type="employee_id",
                    original_value=s,
                    normalized_value=s.upper(),
                    confidence=0.92,
                    recognizer=self.name,
                    reason="employee_id column+prefix",
                    source=ctx.source,
                    start=None,
                    end=None,
                    column=ctx.column,
                    sheet=ctx.sheet,
                    page=ctx.page,
                    rule_version=rule.version,
                    subtype="",
                    validation_status=ValidationStatus.VALID.value,
                    evidence="column+prefix",
                    scope=ctx.path,
                )
            ]
        out = []
        for start, end, orig in find_employee_ids(text, prefixes):
            out.append(
                DetectionResult(
                    entity_type="employee_id",
                    original_value=orig,
                    normalized_value=orig.upper(),
                    confidence=0.88,
                    recognizer=self.name,
                    reason="employee_id prefix/context",
                    source=ctx.source,
                    start=start,
                    end=end,
                    column=ctx.column,
                    sheet=ctx.sheet,
                    page=ctx.page,
                    rule_version=rule.version,
                    subtype="",
                    validation_status=ValidationStatus.VALID.value,
                    evidence="context" if not orig.upper().startswith(prefixes) else "prefix",
                    scope=ctx.path,
                )
            )
        return out
