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
from maskit.rules.engine import _apply_single


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

    rules = _scanable_rules(ruleset)
    if not rules:
        return text

    # 编译所有扫描正则（去锚点）
    compiled = [
        (rule, re.compile(_strip_anchors(rule.match)))
        for rule in rules
    ]

    # 逐个规则替换，避免规则间互相污染
    out = text
    for rule, regex in compiled:
        def _repl(m: re.Match, r=rule) -> str:
            return _apply_single(r, m.group(0), strategy, pepper)

        out = regex.sub(_repl, out)

    # 可选：name/company 识别（语义前缀 + 词表 + 外部清单，纯本地）
    if scan_names:
        out = _mask_names(out, ruleset, pepper, strategy, person_list)

    return out


def _mask_names(
    text: str,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str,
    person_list: set[str] | None = None,
) -> str:
    """用语义前缀 + 词表识别 name/company 并替换（纯本地零网络）。"""
    from maskit.rules.name_company import find_company_names, find_person_names

    name_rule = ruleset.defs.get("name")
    company_rule = ruleset.defs.get("company")
    if not name_rule and not company_rule:
        return text

    out = text
    # 识别到的人名 → 替换
    for name in find_person_names(out, person_list):
        if name_rule:
            out = out.replace(
                name,
                _apply_single(name_rule, name, strategy, pepper),
            )
    # 公司名 → 替换
    for comp in find_company_names(out):
        if company_rule:
            out = out.replace(
                comp,
                _apply_single(company_rule, comp, strategy, pepper),
            )
    return out


def has_scanable_rules(ruleset: RuleSet) -> bool:
    """文本格式（邮件/PDF/Word）是否有可用的扫描规则。"""
    return len(_scanable_rules(ruleset)) > 0
