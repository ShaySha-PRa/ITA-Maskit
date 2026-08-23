"""App version: positive context or leading v. Bare decimals are not versions."""

from __future__ import annotations

import re

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.patterns import DATE_LIKE_VERSION_RE
from maskit.detection.phone import is_date_like
from maskit.detection.result import DetectionResult
from maskit.detection.scope import ValidationStatus


def _is_ip_shaped(value: str) -> bool:
    body = value.strip()
    if body[:1] in "vV":
        body = body[1:]
    parts = body.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

# At least one dot-group, optional leading v.
_VERSION_TOKEN = re.compile(r"\bv?(\d+(?:\.\d+){1,3})\b", re.IGNORECASE)
_V_PREFIX = re.compile(r"\bv(\d+(?:\.\d+){1,3})\b", re.IGNORECASE)
_CONTEXT = re.compile(
    r"(?:版本号|软件版本|版本|version|ver(?:sion)?|build|release)\s*[：:＝=]?\s*",
    re.IGNORECASE,
)
_COLUMN_RE = re.compile(r"^[vV]?\d+(?:\.\d+){1,3}$")


def is_app_version_value(value: str, *, column_mode: bool = False) -> bool:
    s = value.strip()
    if not s or is_date_like(s) or DATE_LIKE_VERSION_RE.fullmatch(s):
        return False
    if column_mode:
        return _COLUMN_RE.fullmatch(s) is not None
    return bool(_V_PREFIX.fullmatch(s) or (s[:1] in "vV" and _COLUMN_RE.fullmatch(s)))


def find_app_versions(text: str) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int]] = set()

    def add(start: int, end: int, orig: str) -> None:
        if is_date_like(orig) or DATE_LIKE_VERSION_RE.fullmatch(orig.strip()):
            return
        if _is_ip_shaped(orig):
            return
        key = (start, end)
        if key in seen:
            return
        seen.add(key)
        hits.append((start, end, orig))

    for m in _V_PREFIX.finditer(text):
        add(m.start(), m.end(), m.group(0))
    for cm in _CONTEXT.finditer(text):
        rest = text[cm.end() :]
        tm = _VERSION_TOKEN.match(rest)
        if not tm:
            continue
        orig = tm.group(0)
        add(cm.end() + tm.start(), cm.end() + tm.end(), orig)
    return hits


class AppVersionRecognizer(Recognizer):
    name = "app_version"

    def detect(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        if not text:
            return []
        rule = ctx.ruleset.defs.get("app_version")
        if rule is None or rule.default_disabled:
            return []
        column_mode = ctx.mapped_rule is not None and ctx.mapped_rule.name == "app_version"
        if ctx.path == "structured" and not column_mode:
            return []
        if column_mode and ctx.path == "structured":
            s = text.strip()
            if not is_app_version_value(s, column_mode=True):
                return []
            return [
                DetectionResult(
                    entity_type="app_version",
                    original_value=s,
                    normalized_value=s.lower(),
                    confidence=0.90,
                    recognizer=self.name,
                    reason="app_version column",
                    source=ctx.source,
                    start=None,
                    end=None,
                    column=ctx.column,
                    sheet=ctx.sheet,
                    page=ctx.page,
                    rule_version=rule.version,
                    subtype="",
                    validation_status=ValidationStatus.VALID.value,
                    evidence="column+validator",
                    scope=ctx.path,
                )
            ]
        out = []
        for start, end, orig in find_app_versions(text):
            out.append(
                DetectionResult(
                    entity_type="app_version",
                    original_value=orig,
                    normalized_value=orig.lower(),
                    confidence=0.86,
                    recognizer=self.name,
                    reason="app_version context",
                    source=ctx.source,
                    start=start,
                    end=end,
                    column=ctx.column,
                    sheet=ctx.sheet,
                    page=ctx.page,
                    rule_version=rule.version,
                    subtype="",
                    validation_status=ValidationStatus.VALID.value,
                    evidence="context",
                    scope=ctx.path,
                )
            )
        return out
