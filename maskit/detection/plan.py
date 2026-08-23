"""Reusable detection/transform plan so preview and execute share bindings."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from maskit.detection.scope import DETECTOR_VERSION
from maskit.rules.defs import RuleDef, RuleSet, RuleSpec


@dataclass(frozen=True)
class ColumnBinding:
    column: str
    rule: str
    strategy: str
    bind_mode: str  # validate | force
    origin: str  # explicit | inferred


@dataclass
class DetectionPlan:
    ruleset_version: str
    detector_version: str
    bindings: dict[str, ColumnBinding]
    plan_id: str
    checksum_policy: str = "legacy"

    def binding_for(self, column: str) -> ColumnBinding | None:
        return self.bindings.get(column)


def compile_column_plan(
    columns: list[str],
    ruleset: RuleSet,
    *,
    checksum_policy: str = "legacy",
) -> DetectionPlan:
    """Build per-column bindings. Inferred auto-match never uses force."""
    from maskit.rules.matcher import auto_match_columns

    bindings: dict[str, ColumnBinding] = {}
    effective: list[RuleSpec] = []
    for spec in ruleset.specs:
        if spec.column not in columns:
            if spec.optional:
                continue
            raise ValueError(f"规则引用了不存在的列: {spec.column!r}")
        effective.append(spec)
    if (not effective and ruleset.specs and all(s.optional for s in ruleset.specs)) or (
        not ruleset.specs
    ):
        effective = auto_match_columns(columns)

    for spec in effective:
        mode = spec.bind_mode or "validate"
        origin = spec.origin or "explicit"
        if origin == "inferred":
            mode = "validate"
        bindings[spec.column] = ColumnBinding(
            column=spec.column,
            rule=spec.rule,
            strategy=spec.strategy,
            bind_mode=mode,
            origin=origin,
        )
    raw = "|".join(
        f"{b.column}:{b.rule}:{b.strategy}:{b.bind_mode}:{b.origin}"
        for b in bindings.values()
    )
    plan_id = sha256(
        f"{ruleset.version}|{DETECTOR_VERSION}|{checksum_policy}|{raw}".encode()
    ).hexdigest()[:16]
    return DetectionPlan(
        ruleset_version=ruleset.version,
        detector_version=DETECTOR_VERSION,
        bindings=bindings,
        plan_id=plan_id,
        checksum_policy=checksum_policy,
    )


def mapped_rule_for(plan: DetectionPlan, ruleset: RuleSet, column: str) -> RuleDef | None:
    b = plan.binding_for(column)
    if b is None:
        return None
    return ruleset.defs.get(b.rule)
