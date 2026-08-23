"""Regex + writing-variant recognizer (email / IP / id_card / bank_card, plus document scan)."""

from __future__ import annotations

import re

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.canonical import canonical_for_rule, to_halfwidth
from maskit.detection.patterns import (
    CELL_IP_RE,
    DASHED_BANK_RE,
    EMAIL_BODY_RE,
    SPACED_ID_RE,
    VALUE_SCAN_RULES,
    strip_anchors,
)
from maskit.detection.result import DetectionResult
from maskit.rules.defs import RuleDef

_CONF = {
    "email": 0.92,
    "ip": 0.93,
    "id_card": 0.80,
    "bank_card": 0.80,
    "phone": 0.90,
    "employee_id": 0.70,
    "app_version": 0.65,
}


def _is_ip_shaped(value: str) -> bool:
    """v10.20.30.40 / 10.20.30.40 视为 IP 形态，避免 phone/app_version 抢匹配。"""
    body = value.strip()
    if body[:1] in "vV":
        body = body[1:]
    parts = body.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


class RegexRecognizer(Recognizer):
    name = "regex"

    def __init__(self, mode: str = "search"):
        if mode not in {"search", "fullmatch"}:
            raise ValueError(f"illegal RegexRecognizer mode: {mode}")
        self.mode = mode

    def detect(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        if not text:
            return []
        if self.mode == "fullmatch":
            return self._fullmatch(text, ctx)
        hits = self._search(text, ctx)
        hits.extend(self._variants(text, ctx))
        return hits

    def _rules(self, ctx: DetectContext) -> list[RuleDef]:
        # Strong features only. phone / employee_id / app_version have dedicated recognizers.
        names = VALUE_SCAN_RULES
        return [
            d
            for name in names
            if (d := ctx.ruleset.defs.get(name)) is not None and not d.default_disabled
        ]

    def _fullmatch(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        s = text.strip()
        if not s or s.startswith("="):
            return []
        best: DetectionResult | None = None
        best_len = -1
        for rule in self._rules(ctx):
            cand = canonical_for_rule(rule, s)
            try:
                ok = re.fullmatch(rule.match, cand) is not None
            except re.error:
                continue
            if ok and len(rule.match) > best_len:
                best_len = len(rule.match)
                best = self._make(rule, s, cand, ctx, start=None, end=None)
        return [best] if best else []

    def _search(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        hits: list[DetectionResult] = []
        seen: set[str] = set()
        for rule in self._rules(ctx):
            if rule.name == "ip":
                regex, scan = CELL_IP_RE, text
            else:
                regex, scan = re.compile(strip_anchors(rule.match)), text
            for m in regex.finditer(scan):
                original = text[m.start() : m.end()]
                if original in seen:
                    continue
                seen.add(original)
                hits.append(
                    self._make(
                        rule,
                        original,
                        canonical_for_rule(rule, original),
                        ctx,
                        start=m.start(),
                        end=m.end(),
                    )
                )
        return hits

    def _variants(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        hits: list[DetectionResult] = []
        id_rule = ctx.ruleset.defs.get("id_card")
        bank_rule = ctx.ruleset.defs.get("bank_card")
        email_rule = ctx.ruleset.defs.get("email")
        if id_rule and not id_rule.default_disabled:
            for m in SPACED_ID_RE.finditer(text):
                compact = re.sub(r"\s+", "", m.group(0))
                hits.append(
                    self._make(id_rule, m.group(0), compact, ctx, m.start(), m.end())
                )
        if bank_rule and not bank_rule.default_disabled:
            for m in DASHED_BANK_RE.finditer(text):
                digits = re.sub(r"[\s\-]", "", m.group(0))
                if 16 <= len(digits) <= 19:
                    hits.append(
                        self._make(bank_rule, m.group(0), digits, ctx, m.start(), m.end())
                    )
        if email_rule and not email_rule.default_disabled:
            half = to_halfwidth(text)
            if half != text:
                for m in EMAIL_BODY_RE.finditer(half):
                    orig = text[m.start() : m.end()]
                    if orig == m.group(0):
                        continue
                    hits.append(
                        self._make(email_rule, orig, m.group(0), ctx, m.start(), m.end())
                    )
        return hits

    def _make(
        self,
        rule: RuleDef,
        original: str,
        normalized: str,
        ctx: DetectContext,
        start: int | None,
        end: int | None,
    ) -> DetectionResult:
        conf = _CONF.get(rule.name, 0.75)
        return DetectionResult(
            entity_type=rule.name,
            original_value=original,
            normalized_value=normalized,
            confidence=conf,
            recognizer=self.name,
            reason=f"regex {self.mode} {rule.name}",
            source=ctx.source,
            start=start,
            end=end,
            column=ctx.column,
            sheet=ctx.sheet,
            page=ctx.page,
            rule_version=rule.version,
        )
