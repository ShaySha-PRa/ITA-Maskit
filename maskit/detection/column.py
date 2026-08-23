"""Column-name recognizer: mapped spec or keyword auto-match + value fullmatch."""

from __future__ import annotations

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.canonical import canonical_for_rule, value_matches_rule
from maskit.detection.result import DetectionResult
from maskit.rules.name_company import COMMON_NON_NAMES


class ColumnRecognizer(Recognizer):
    name = "column"

    def detect(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        rule = ctx.mapped_rule
        if rule is None:
            return []
        if not value_matches_rule(rule, text, COMMON_NON_NAMES):
            return []
        s = text.strip()
        norm = canonical_for_rule(rule, s)
        return [
            DetectionResult(
                entity_type=rule.name,
                original_value=s,
                normalized_value=norm,
                confidence=0.95,
                recognizer=self.name,
                reason=f"column {ctx.column!r} mapped to {rule.name}",
                source="column",
                start=None,
                end=None,
                column=ctx.column,
                sheet=ctx.sheet,
                page=ctx.page,
                rule_version=rule.version,
            )
        ]
