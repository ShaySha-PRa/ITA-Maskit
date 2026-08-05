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
    )


def load_ruleset(yaml_path: str | Path | None = None) -> RuleSet:
    """加载规则集。

    无 yaml_path → 用内置定义 + 默认列映射（全部 mask）。
    有 yaml_path → 内置定义为基础，YAML 的 rule_defs 覆盖/新增；
                   rules 段做列映射。
    """
    defs: dict[str, RuleDef] = {
        name: _build_rule_def(name, raw) for name, raw in BUILTIN_RULE_DEFS.items()
    }

    if yaml_path is None:
        # 默认规则集：对存在的敏感列脱敏（optional=True，缺列静默跳过）
        specs = [RuleSpec(**m, optional=True) for m in DEFAULT_MAPPING]
    else:
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"规则文件不存在: {path}")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"规则文件 YAML 解析失败: {path} ({exc})") from exc

        # ① rule_defs：覆盖/新增规则定义
        for name, raw in (data.get("rule_defs") or {}).items():
            defs[name] = _build_rule_def(name, raw)

        # ② rules：列映射
        specs = [RuleSpec(**m) for m in (data.get("rules") or [])]

    ruleset = RuleSet(defs=defs, specs=specs)
    # 校验（列映射引用的规则存在、策略合法）
    for spec in specs:
        spec.validate(set(defs.keys()))
    return ruleset


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
