"""文本 PII 识别 + 替换引擎（邮件正文 / PDF / Word）。

在文本流中扫描「可用于全文扫描」的规则（text_scanable=True，即有精确正则
的 email/ip/phone/employee_id/app_version/ssn/credit_card），对匹配处替换成
mask/pseudo 模板。

name/company（match 过宽无法直接全文扫描）通过可选参数 `scan_names` 启用：
用语义前缀 + 内置词表识别（见 maskit.rules.name_company），纯本地零网络。
"""
from __future__ import annotations

import re

from maskit.rules.defs import RuleDef, RuleSet
from maskit.rules.engine import (
    CELL_IP_RE,
    _apply_single,
    iter_pii_variant_hits,
)


def _strip_anchors(pattern: str) -> str:
    """去掉 ^ 和 $ 锚点，使规则正则可在文本流内匹配。"""
    p = pattern
    p = p.removeprefix("^")
    p = p.removesuffix("$")
    return p


def _scanable_rules(ruleset: RuleSet) -> list[RuleDef]:
    """返回可用于文本扫描的规则（text_scanable 且非默认关闭）。"""
    return [
        d
        for d in ruleset.defs.values()
        if d.text_scanable and not d.default_disabled
    ]


def _is_ip_shaped(value: str) -> bool:
    """v10.20.30.40 / 10.20.30.40（可带尾空白）视为 IP 形态，避免 phone/app_version 抢匹配。"""
    body = value.strip()
    if body[:1] in "vV":
        body = body[1:]
    parts = body.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def _text_scan_regex(rule: RuleDef) -> re.Pattern:
    """文本流正则：IP 用带边界的格内正则，避免 v10.20.30.40。"""
    if rule.name == "ip":
        return CELL_IP_RE
    return re.compile(_strip_anchors(rule.match))


def mask_text_pii(
    text: str,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
    scan_names: bool = False,
    person_list: set[str] | None = None,
) -> str:
    """对文本流中的 PII 做 mask/pseudo 替换，返回脱敏后的文本。

    - 只扫描 text_scanable 规则
    - strategy="mask"（默认，无需 pepper）或 "pseudo"（确定性，需 pepper）
    - scan_names=True → 额外用语义前缀 + 词表识别 name/company（纯本地）
    - person_list：外部全量人员清单（动态词表），识别不易从上下文判断的人名
    - 每个匹配独立替换，匹配处去锚点后编译
    """
    if not text:
        return text
    out = text
    for original, replacement in _iter_regex_and_variant_hits(
        text, ruleset, pepper, strategy
    ):
        out = out.replace(original, replacement)
    if scan_names:
        out = _mask_names(out, ruleset, pepper, strategy, person_list)
    return out


def _iter_regex_and_variant_hits(
    text: str,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str,
) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rule in _scanable_rules(ruleset):
        regex = _text_scan_regex(rule)
        for m in regex.finditer(text):
            original = m.group(0)
            if rule.name in {"phone", "app_version"} and _is_ip_shaped(original):
                continue
            if original in seen:
                continue
            seen.add(original)
            hits.append((original, _apply_single(rule, original, strategy, pepper)))
    by_name = {
        d.name: d
        for d in ruleset.defs.values()
        if not d.default_disabled
    }
    for original, replacement in iter_pii_variant_hits(text, by_name, strategy, pepper):
        if original not in seen:
            seen.add(original)
            hits.append((original, replacement))
    hits.sort(key=lambda pair: len(pair[0]), reverse=True)
    return hits


def iter_text_pii_hits(
    text: str,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
    scan_names: bool = False,
    person_list: set[str] | None = None,
) -> list[tuple[str, str]]:
    """找出文本中的 PII 命中，返回 [(原文, 替换文), ...]（去重，长串优先）。

    供 PDF 原样遮罩等需要定位原文矩形的路径使用。
    """
    if not text:
        return []

    hits = _iter_regex_and_variant_hits(text, ruleset, pepper, strategy)
    seen = {original for original, _ in hits}

    if scan_names:
        from maskit.rules.name_company import (
            BUILTIN_NAMES,
            find_company_names,
            iter_person_list_spans,
        )

        name_rule = ruleset.defs.get("name")
        company_rule = ruleset.defs.get("company")
        if name_rule:
            names = set(BUILTIN_NAMES) | (person_list or set())
            for _, _, name in iter_person_list_spans(text, names):
                if name not in seen:
                    seen.add(name)
                    hits.append((name, _apply_single(name_rule, name, strategy, pepper)))
        if company_rule:
            for comp in find_company_names(text):
                if comp not in seen:
                    seen.add(comp)
                    hits.append((comp, _apply_single(company_rule, comp, strategy, pepper)))

    hits.sort(key=lambda pair: len(pair[0]), reverse=True)
    return hits


def _mask_names(
    text: str,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str,
    person_list: set[str] | None = None,
) -> str:
    """用语义前缀 + 词表识别 name/company 并替换（纯本地零网络）。"""
    from maskit.rules.name_company import (
        BUILTIN_NAMES,
        find_company_names,
        find_person_names,
        mask_person_list_in_text,
    )

    name_rule = ruleset.defs.get("name")
    company_rule = ruleset.defs.get("company")
    if not name_rule and not company_rule:
        return text

    out = text
    if name_rule:
        names = set(BUILTIN_NAMES) | (person_list or set())
        out = mask_person_list_in_text(
            out,
            names,
            lambda n, nr=name_rule: _apply_single(nr, n, strategy, pepper),
        )
        # 语义前缀命中、但不在词表里的名字（按捕获组位置替换，避免全局子串误伤）
        listed = set(names)
        prefix_names = [
            n for n in find_person_names(out, person_list) if n not in listed
        ]
        for name in sorted(prefix_names, key=len, reverse=True):
            out = out.replace(name, _apply_single(name_rule, name, strategy, pepper))
    if company_rule:
        for comp in find_company_names(out):
            out = out.replace(
                comp,
                _apply_single(company_rule, comp, strategy, pepper),
            )
    return out


def has_scanable_rules(ruleset: RuleSet) -> bool:
    """文本格式（邮件/PDF/Word）是否有可用的扫描规则。"""
    return len(_scanable_rules(ruleset)) > 0
