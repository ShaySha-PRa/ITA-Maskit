"""Entity canonicalization used by both detection and transformation."""

from __future__ import annotations

import re

from maskit.detection.employee import looks_like_employee_id
from maskit.detection.patterns import CATCHALL_BODIES, DATE_LIKE_VERSION_RE, DEPT_LIKE_RE
from maskit.detection.phone import is_phone_value
from maskit.detection.scope import DEFAULT_EMPLOYEE_PREFIXES
from maskit.detection.version import is_app_version_value
from maskit.rules.defs import RuleDef


def to_halfwidth(s: str) -> str:
    """全角 ASCII（FF01-FF5E）按位映射为半角，下标 1:1。"""
    chars = []
    for c in s:
        o = ord(c)
        if 0xFF01 <= o <= 0xFF5E:
            chars.append(chr(o - 0xFEE0))
        elif c == "\u3000":
            chars.append(" ")
        else:
            chars.append(c)
    return "".join(chars)


def canonical_for_rule(rule: RuleDef, raw: str) -> str:
    """列映射/整格检测用的规范化值（空格证号、横线卡号、全角邮箱）。"""
    if rule.name == "id_card":
        return re.sub(r"\s+", "", raw)
    if rule.name == "bank_card":
        return re.sub(r"[\s\-]", "", raw)
    if rule.name == "email":
        return to_halfwidth(raw)
    return raw.strip()


def is_catchall_rule(rule: RuleDef) -> bool:
    body = rule.match.removeprefix("^").removesuffix("$")
    return body in CATCHALL_BODIES


def should_skip_catchall_value(value: str, non_names: set[str]) -> bool:
    """部门/科室或排除词 → 不套 name/company 的 .+ 模板。"""
    s = value.strip()
    if s in non_names:
        return True
    return DEPT_LIKE_RE.fullmatch(s) is not None


def value_matches_rule(rule: RuleDef, value: str, non_names: set[str]) -> bool:
    """值是否整体命中规则（列映射套模板前的校验）。弱类型走专用 validator。"""
    s = value.strip()
    if not s:
        return False
    if is_catchall_rule(rule) and should_skip_catchall_value(s, non_names):
        return False
    if rule.name == "phone":
        return is_phone_value(s, column_mode=True)
    if rule.name == "app_version":
        return is_app_version_value(s, column_mode=True)
    if rule.name == "employee_id":
        prefixes = tuple(
            p.upper() for p in (getattr(rule, "prefixes", None) or DEFAULT_EMPLOYEE_PREFIXES)
        )
        return looks_like_employee_id(s, prefixes, column_mode=True)
    if rule.name == "app_version" and DATE_LIKE_VERSION_RE.fullmatch(s):
        return False
    cand = canonical_for_rule(rule, s)
    try:
        return re.fullmatch(rule.match, cand) is not None
    except re.error:
        return False
