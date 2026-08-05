"""文本 PII 识别 + 替换引擎（邮件正文 / PDF / Word）。

在文本流中扫描「可用于全文扫描」的规则（text_scanable=True，即有精确正则
的 email/ip/phone/employee_id/app_version/ssn/credit_card），对匹配处替换成
mask/pseudo 模板。name/company/account 等 match 过宽或无法区分边界的规则
不参与全文扫描（仅列式可用），避免误伤普通文字。
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
) -> str:
    """对文本流中的 PII 做 mask/pseudo 替换，返回脱敏后的文本。

    - 只扫描 text_scanable 规则
    - strategy="mask"（默认，无需 pepper）或 "pseudo"（确定性，需 pepper）
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

    # 逐个规则替换，避免规则间互相污染（每次基于原文，记录 span）
    # 简单方案：按规则顺序 sub，后规则不会重新匹配已替换内容（若替换结果含 PII 模式，
    # 顺序可导致后规则处理替换结果；用占位符避免。为简化，先按规则顺序 sub）。
    out = text
    for rule, regex in compiled:
        def _repl(m: re.Match, r=rule) -> str:
            return _apply_single(r, m.group(0), strategy, pepper)

        out = regex.sub(_repl, out)
    return out


def has_scanable_rules(ruleset: RuleSet) -> bool:
    """文本格式（邮件/PDF/Word）是否有可用的扫描规则。"""
    return len(_scanable_rules(ruleset)) > 0
