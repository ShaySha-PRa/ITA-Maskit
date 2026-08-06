"""YAML 规则集加载。

数据驱动规则：内置定义作默认值，YAML 的 rule_defs 可覆盖/新增，
rules 段做列映射。规则带版本号，审计可追溯。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from maskit.rules.defs import BUILTIN_RULE_DEFS, RuleDef, RuleSet, RuleSpec

# 默认列映射（无 --rules 时使用的内置规则集，全部 mask 策略）
DEFAULT_MAPPING: list[dict[str, str]] = [
    {"column": "name", "rule": "name", "strategy": "mask"},
    {"column": "email", "rule": "email", "strategy": "mask"},
    {"column": "ip", "rule": "ip", "strategy": "mask"},
    {"column": "phone", "rule": "phone", "strategy": "mask"},
    {"column": "employee_id", "rule": "employee_id", "strategy": "mask"},
    {"column": "account", "rule": "account", "strategy": "mask"},
    {"column": "company", "rule": "company", "strategy": "mask"},
    {"column": "app_version", "rule": "app_version", "strategy": "mask"},
]


def _build_rule_def(name: str, raw: dict[str, Any]) -> RuleDef:
    """把原始 dict 转成 RuleDef，校验必填字段。"""
    missing = [k for k in ("match", "mask", "pseudo") if k not in raw]
    if missing:
        raise ValueError(f"规则 {name!r} 缺少字段: {missing}")
    return RuleDef(
        name=name,
        version=str(raw.get("version", "1.0")),
        match=raw["match"],
        mask=raw["mask"],
        pseudo=raw["pseudo"],
        normalize=raw.get("normalize", "default"),
        default_disabled=bool(raw.get("default_disabled", False)),
        text_scanable=bool(raw.get("text_scanable", False)),
        keywords=list(raw.get("keywords", [])),
        description=raw.get("description", ""),
    )


def _build_ruleset_from_data(data: dict, *, optional_specs: bool = False) -> RuleSet:
    """从解析后的 YAML dict 构建 RuleSet。

    optional_specs=True → 列映射标记 optional（缺列静默跳过），默认规则集用。
    """
    defs: dict[str, RuleDef] = {
        name: _build_rule_def(name, raw) for name, raw in BUILTIN_RULE_DEFS.items()
    }
    # ① rule_defs：覆盖/新增规则定义
    for name, raw in (data.get("rule_defs") or {}).items():
        defs[name] = _build_rule_def(name, raw)
    # ② rules：列映射
    specs = []
    for m in (data.get("rules") or []):
        if optional_specs:
            m = dict(m)
            m.setdefault("optional", True)
        specs.append(RuleSpec(**m))

    ruleset = RuleSet(defs=defs, specs=specs)
    for spec in specs:
        spec.validate(set(defs.keys()))
    return ruleset


def load_ruleset(yaml_path: str | Path | None = None) -> RuleSet:
    """加载规则集。

    无 yaml_path → 内置定义 + 默认列映射（全部 mask）。
    有 yaml_path → 内置定义为基础，YAML 的 rule_defs 覆盖/新增；
                   rules 段做列映射。
    """
    if yaml_path is None:
        # 默认规则集：用内置定义 + 默认列映射（缺列静默跳过）
        defs = {name: _build_rule_def(name, raw) for name, raw in BUILTIN_RULE_DEFS.items()}
        specs = [RuleSpec(**m, optional=True) for m in DEFAULT_MAPPING]
        return RuleSet(defs=defs, specs=specs)
    else:
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"规则文件不存在: {path}")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"规则文件 YAML 解析失败: {path} ({exc})") from exc
        return _build_ruleset_from_data(data)


def load_ruleset_for_columns(
    columns: list[str],
    base_ruleset: RuleSet | None = None,
    prefer_auto: bool = False,
) -> RuleSet:
    """为指定列名加载规则集：自动匹配列名到规则。

    - 默认（无 rules 时）：用 auto_match_columns 自动匹配
    - base_ruleset 提供规则定义（含内置 + 自定义）
    - prefer_auto=False 且 base_ruleset 有显式 specs 时 → 用显式 specs
      （用户 --rules 显式映射优先）
    """
    base = base_ruleset or load_ruleset()
    # 若已有显式列映射且不强制自动 → 用显式
    if base.specs and not prefer_auto:
        return base
    from maskit.rules.matcher import auto_match_columns

    specs = auto_match_columns(columns)
    return RuleSet(defs=base.defs, specs=specs)


def load_ruleset_from_string(yaml_text: str) -> RuleSet:
    """从 YAML 字符串加载规则集（供 LLM 生成结果校验）。"""
    try:
        data = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"生成的规则 YAML 解析失败: {exc}") from exc
    return _build_ruleset_from_data(data)


def list_rules(ruleset: RuleSet | None = None) -> list[dict[str, Any]]:
    """列出可用规则（供 `maskit rules list`）。"""
    rs = ruleset or load_ruleset()
    return [
        {
            "rule": d.name,
            "version": d.version,
            "match": d.match,
            "mask": d.mask,
            "pseudo": d.pseudo,
            "default_disabled": d.default_disabled,
        }
        for d in sorted(rs.defs.values(), key=lambda d: d.name)
    ]
