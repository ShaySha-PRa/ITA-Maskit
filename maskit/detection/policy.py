"""Write-path policy: detection is not permission to mutate."""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import replace

from maskit.detection.allowlist import Allowlist
from maskit.detection.result import DetectionResult
from maskit.detection.scope import ChecksumPolicy, DecisionAction, ValidationStatus

_checksum_policy: ContextVar[str] = ContextVar("checksum_policy", default="legacy")
_allowlist: ContextVar[Allowlist | None] = ContextVar("allowlist", default=None)


def set_checksum_policy(policy: str):
    return _checksum_policy.set(policy or "legacy")


def current_checksum_policy() -> str:
    return _checksum_policy.get()


def set_allowlist(allowlist: Allowlist | None):
    return _allowlist.set(allowlist)


def current_allowlist() -> Allowlist | None:
    return _allowlist.get()


_CHECKSUM_TYPES = frozenset({"id_card", "bank_card"})


def checksum_should_review(
    rule_name: str, value: str, policy: str | None = None
) -> bool:
    """True when INVALID checksum must not auto-write (review/strict)."""
    pol = policy if policy is not None else current_checksum_policy()
    if pol == ChecksumPolicy.LEGACY.value:
        return False
    if rule_name == "id_card":
        from maskit.detection.checksum import id_card_checksum_ok

        compact = re.sub(r"\s+", "", value).upper()
        if not re.fullmatch(r"\d{17}[\dX]", compact):
            return False
        return not id_card_checksum_ok(compact)
    if rule_name == "bank_card":
        from maskit.detection.checksum import luhn_ok

        digits = re.sub(r"[\s\-]", "", value)
        if not digits.isdigit() or not (16 <= len(digits) <= 19):
            return False
        return not luhn_ok(digits)
    return False


def decide_hit(
    hit: DetectionResult,
    *,
    checksum_policy: str = ChecksumPolicy.LEGACY.value,
    bind_mode: str = "validate",
) -> DetectionResult:
    """Attach DecisionAction. Does not transform."""
    policy = checksum_policy or ChecksumPolicy.LEGACY.value
    action = DecisionAction.AUTO_APPLY.value
    al = current_allowlist()
    if al is not None:
        from maskit.detection.review import fingerprint as _fp

        allowed = al.allows(
            hit.entity_type,
            hit.original_value,
            fingerprint=_fp(hit.original_value),
        )
    else:
        allowed = False
    if allowed:
        action = DecisionAction.REJECT.value
    elif bind_mode == "force":
        action = DecisionAction.AUTO_APPLY.value
    elif hit.entity_type in _CHECKSUM_TYPES and hit.validation_status == ValidationStatus.INVALID.value:
        if policy == ChecksumPolicy.LEGACY.value:
            action = DecisionAction.AUTO_APPLY.value
        elif policy in {ChecksumPolicy.REVIEW.value, ChecksumPolicy.STRICT.value}:
            action = DecisionAction.REVIEW.value
        else:
            action = DecisionAction.REVIEW.value
    elif hit.validation_status == ValidationStatus.INVALID.value and policy != ChecksumPolicy.LEGACY.value:
        action = DecisionAction.REVIEW.value
    try:
        return replace(hit, decision=action)
    except TypeError:
        return hit


def partition_hits(
    hits: list[DetectionResult],
    *,
    checksum_policy: str = ChecksumPolicy.LEGACY.value,
    bind_mode: str = "validate",
) -> dict[str, list[DetectionResult]]:
    decided = [decide_hit(h, checksum_policy=checksum_policy, bind_mode=bind_mode) for h in hits]
    buckets = {
        DecisionAction.AUTO_APPLY.value: [],
        DecisionAction.REVIEW.value: [],
        DecisionAction.REJECT.value: [],
    }
    for h in decided:
        buckets.setdefault(h.decision or DecisionAction.AUTO_APPLY.value, []).append(h)
    return buckets
