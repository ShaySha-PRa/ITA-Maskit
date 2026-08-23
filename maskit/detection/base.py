"""Recognizer interface and per-call context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maskit.detection.result import DetectionResult

if TYPE_CHECKING:
    from maskit.rules.defs import RuleDef, RuleSet


@dataclass
class DetectContext:
    """Inputs shared by all recognizers for one cell or text chunk."""

    ruleset: RuleSet
    column: str | None = None
    mapped_rule: RuleDef | None = None
    person_list: set[str] | None = None
    scan_names: bool = False
    source: str = "cell"
    sheet: str | None = None
    page: int | None = None
    path: str = "structured"  # structured | document
    extra: dict = field(default_factory=dict)


class Recognizer:
    """Base recognizer. detect() must not transform the text."""

    name = "base"

    def detect(self, text: str, ctx: DetectContext) -> list[DetectionResult]:
        raise NotImplementedError
