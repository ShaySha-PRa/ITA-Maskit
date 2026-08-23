"""Dictionary / person-list recognizer. No cloud, no NER."""

from __future__ import annotations

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.result import DetectionResult
from maskit.rules.name_company import (
    BUILTIN_NAMES,
    find_company_names,
    find_person_names,
    is_person_name,
    iter_person_list_spans,
)


class DictionaryRecognizer(Recognizer):
    name = "dictionary"

    def __init__(self, mode: str = "span"):
        if mode not in {"span", "exact"}:
            raise ValueError(f"illegal DictionaryRecognizer mode: {mode}")
        self.mode = mode

    def detect(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        if not text.strip():
            return []
        name_rule = ctx.ruleset.defs.get("name")
        if self.mode == "exact":
            return self._exact(text, ctx, name_rule)
        hits = self._spans(text, ctx, name_rule)
        if ctx.scan_names:
            hits.extend(self._scan_names(text, ctx, name_rule))
        return hits

    def _exact(self, text: str, ctx: DetectContext, name_rule) -> list[DetectionResult]:
        if name_rule is None:
            return []
        s = text.strip()
        if ctx.person_list and s in ctx.person_list:
            return [self._hit(name_rule, s, s, ctx, None, None, 0.98, "person-list exact")]
        if not ctx.person_list and is_person_name(s):
            return [
                self._hit(
                    name_rule, s, s, ctx, None, None, 0.72, "surname heuristic (no list)"
                )
            ]
        return []

    def _spans(self, text: str, ctx: DetectContext, name_rule) -> list[DetectionResult]:
        if name_rule is None or not ctx.person_list:
            return []
        hits: list[DetectionResult] = []
        for start, end, name in iter_person_list_spans(text, ctx.person_list):
            hits.append(
                self._hit(name_rule, name, name, ctx, start, end, 0.97, "person-list span")
            )
        return hits

    def _scan_names(self, text: str, ctx: DetectContext, name_rule) -> list[DetectionResult]:
        hits: list[DetectionResult] = []
        names = set(ctx.person_list) if ctx.person_list else set(BUILTIN_NAMES)
        if name_rule:
            listed = set()
            for start, end, name in iter_person_list_spans(text, names):
                listed.add(name)
                hits.append(
                    self._hit(
                        name_rule, name, name, ctx, start, end, 0.96, "name gazetteer"
                    )
                )
            for name in find_person_names(text, ctx.person_list):
                if name in listed:
                    continue
                if ctx.person_list and name not in ctx.person_list:
                    continue
                idx = text.find(name)
                if idx < 0:
                    continue
                hits.append(
                    self._hit(
                        name_rule,
                        name,
                        name,
                        ctx,
                        idx,
                        idx + len(name),
                        0.82,
                        "semantic prefix name",
                    )
                )
        company_rule = ctx.ruleset.defs.get("company")
        if company_rule:
            for comp in find_company_names(text):
                idx = text.find(comp)
                if idx < 0:
                    continue
                hits.append(
                    DetectionResult(
                        entity_type="company",
                        original_value=comp,
                        normalized_value=comp,
                        confidence=0.82,
                        recognizer=self.name,
                        reason="semantic prefix/gazetteer company",
                        source=ctx.source,
                        start=idx,
                        end=idx + len(comp),
                        column=ctx.column,
                        sheet=ctx.sheet,
                        page=ctx.page,
                        rule_version=company_rule.version,
                    )
                )
        return hits

    def _hit(
        self, rule, original, normalized, ctx, start, end, conf, reason
    ) -> DetectionResult:
        return DetectionResult(
            entity_type=rule.name,
            original_value=original,
            normalized_value=normalized,
            confidence=conf,
            recognizer=self.name,
            reason=reason,
            source=ctx.source,
            start=start,
            end=end,
            column=ctx.column,
            sheet=ctx.sheet,
            page=ctx.page,
            rule_version=rule.version,
        )
