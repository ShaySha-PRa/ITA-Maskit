"""列名自动匹配规则（通用性增强）。

不同公司/文件的列名都不一样（姓名/Name/员工姓名/签约主体…），
用「语义关键词」自动把列名匹配到规则，无需用户写规则。

匹配逻辑：
- 列名小写化 + 去空白
- 遍历所有规则的 keywords，找含该关键词的列
- 一列名可能含多个关键词（「员工姓名」含 name 和 employee_id）
  → 取**最长关键词**（更具体优先）
- 无匹配的列 → 不脱敏（原样透传）
"""
from __future__ import annotations

from maskit.rules.defs import BUILTIN_RULE_DEFS, RuleSpec


def _normalize(name: str) -> str:
    """列名归一：小写 + 去空白 + 去下划线。"""
    return name.strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def _build_keyword_index() -> list[tuple[str, str]]:
    """构建 (关键词归一化, 规则名) 索引，按关键词长度降序（最长优先）。"""
    index = []
    for rule_name, raw in BUILTIN_RULE_DEFS.items():
        if raw.get("default_disabled"):
            continue  # ssn/credit_card 默认关闭，不参与自动匹配
        for kw in raw.get("keywords", []):
            index.append((_normalize(kw), rule_name))
    # 最长关键词优先
    index.sort(key=lambda item: len(item[0]), reverse=True)
    return index


def auto_match_columns(columns: list[str]) -> list[RuleSpec]:
    """按列名自动匹配规则，返回列映射 specs。

    - 每列匹配命中关键词最长的规则
    - 无匹配列不生成 spec（原样透传）
    """
    keyword_index = _build_keyword_index()
    specs = []
    for col in columns:
        norm_col = _normalize(str(col))
        if not norm_col:
            continue
        matched = None
        for norm_kw, rule_name in keyword_index:
            if norm_kw and norm_kw in norm_col:
                matched = rule_name
                break
        if matched:
            specs.append(RuleSpec(column=str(col), rule=matched, strategy="mask"))
    return specs


def auto_match_specs_for(columns: list[str]) -> list[dict]:
    """返回可序列化的列映射（供调试/展示）。"""
    return [
        {"column": s.column, "rule": s.rule, "strategy": s.strategy}
        for s in auto_match_columns(columns)
    ]
