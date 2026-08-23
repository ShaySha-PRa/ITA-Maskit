"""文本 PII 识别 + 替换引擎（邮件正文 / PDF / Word）。

Detection 走 maskit.detection.detect_text；替换仍用规则模板 / HMAC。
"""

from __future__ import annotations

from maskit.detection.patterns import strip_anchors as _strip_anchors
from maskit.detection.pipeline import detect_text
from maskit.rules.defs import RuleDef, RuleSet
from maskit.rules.engine import _apply_detections, _apply_single, _apply_src


def _scanable_rules(ruleset: RuleSet) -> list[RuleDef]:
    """返回可用于文本扫描的规则（text_scanable 且非默认关闭）。"""
    return [
        d
        for d in ruleset.defs.values()
        if d.text_scanable and not d.default_disabled
    ]


def mask_text_pii(
    text: str,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
    scan_names: bool = False,
    person_list: set[str] | None = None,
    checksum_policy: str | None = None,
) -> str:
    """对文本流中的 PII 做 mask/pseudo 替换，返回脱敏后的文本。"""
    if not text:
        return text
    hits = detect_text(
        text, ruleset=ruleset, person_list=person_list, scan_names=scan_names
    )
    from maskit.detection.policy import current_checksum_policy, partition_hits

    policy = checksum_policy if checksum_policy is not None else current_checksum_policy()
    parts = partition_hits(hits, checksum_policy=policy)
    from maskit.detection.runctx import current_run

    stats = current_run()
    stats.auto_apply += len(parts["AUTO_APPLY"])
    stats.reject += len(parts["REJECT"])
    for h in parts["REVIEW"]:
        stats.add_review(
            entity_type=h.entity_type,
            value=h.original_value,
            page=h.page,
            column=h.column,
            sheet=h.sheet,
            reason=h.reason,
            validation_status=h.validation_status,
            recognizer=h.recognizer,
            detection_score=h.confidence,
            subtype=h.subtype,
        )
    return _apply_detections(text, parts["AUTO_APPLY"], strategy, pepper, ruleset)["masked_value"]


def iter_text_pii_hits(
    text: str,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
    scan_names: bool = False,
    person_list: set[str] | None = None,
) -> list[tuple[str, str]]:
    """找出文本中的 PII 命中，返回 [(原文, 替换文), ...]（去重，长串优先）。"""
    if not text:
        return []
    detections = detect_text(
        text, ruleset=ruleset, person_list=person_list, scan_names=scan_names
    )
    from maskit.detection.policy import current_checksum_policy, partition_hits

    auto = partition_hits(
        detections, checksum_policy=current_checksum_policy()
    )["AUTO_APPLY"]
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for h in sorted(auto, key=lambda d: len(d.original_value), reverse=True):
        if h.original_value in seen:
            continue
        seen.add(h.original_value)
        rule = ruleset.defs.get(h.entity_type)
        if rule is None:
            continue
        hits.append(
            (h.original_value, _apply_single(rule, _apply_src(h), strategy, pepper))
        )
    return hits


def has_scanable_rules(ruleset: RuleSet) -> bool:
    """文本格式（邮件/PDF/Word）是否有可用的扫描规则。"""
    return len(_scanable_rules(ruleset)) > 0


# OCR 图片路径仍从本模块导入去锚点工具
__all__ = [
    "_strip_anchors",
    "has_scanable_rules",
    "iter_text_pii_hits",
    "mask_text_pii",
]
