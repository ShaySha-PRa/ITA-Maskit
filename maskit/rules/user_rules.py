"""用户规则文件管理（GUI 规则可视化编辑的后端）。

用户规则存于 ~/.maskit/user_rules.yaml（全局，跨项目生效）。
GUI 编辑规则 → 保存到此文件 → 脱敏加载它（覆盖/新增内置规则）。
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from maskit.rules.defs import BUILTIN_RULE_DEFS, RuleSet, RuleSpec
from maskit.rules.loader import DEFAULT_MAPPING, _build_rule_def

# 用户规则文件路径（全局）
USER_RULES_PATH = Path.home() / ".maskit" / "user_rules.yaml"

# 规则定义必填字段
_REQUIRED_FIELDS = ("match", "mask", "pseudo")


def user_rules_path() -> Path:
    """用户规则文件路径（可用 MASKIT_USER_RULES 覆盖）。"""
    import os

    override = os.environ.get("MASKIT_USER_RULES")
    if override:
        return Path(override)
    return USER_RULES_PATH


def get_rule_defs() -> dict[str, dict[str, Any]]:
    """返回当前生效规则定义（内置 + 用户覆盖/新增）。

    用户文件的 rule_defs 覆盖内置（同名）或新增（新名）。
    """
    defs = {name: dict(raw) for name, raw in BUILTIN_RULE_DEFS.items()}
    path = user_rules_path()
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        for name, raw in (data.get("rule_defs") or {}).items():
            defs[name] = dict(raw)
    return defs


def validate_rule_def(name: str, raw: dict[str, Any]) -> None:
    """校验单条规则定义。

    - 必填 match/mask/pseudo
    - match 必须是合法 Python 正则（预编译检查）
    """
    if not name or not name.strip():
        raise ValueError("规则名不能为空")
    missing = [f for f in _REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ValueError(f"规则 {name!r} 缺少字段: {missing}")
    # 正则预编译检查
    try:
        re.compile(str(raw["match"]))
    except re.error as exc:
        raise ValueError(f"规则 {name!r} 的正则非法: {exc}")
    _build_rule_def(name, raw)  # 复用 loader 的完整校验


def save_user_rules(defs: dict[str, dict[str, Any]]) -> None:
    """保存规则定义到用户规则文件（原子写：temp + rename）。

    只保存 rule_defs 段（列映射由脱敏时自动匹配，无需用户维护）。
    """
    path = user_rules_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 校验所有规则
    for name, raw in defs.items():
        validate_rule_def(name, raw)
    # 原子写
    data = {"rule_defs": {name: dict(raw) for name, raw in defs.items()}}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        Path(tmp).replace(path)
    finally:
        try:
            Path(tmp).unlink()
        except OSError:
            pass


def delete_user_rules() -> None:
    """删除用户规则文件（恢复内置默认）。"""
    path = user_rules_path()
    if path.exists():
        path.unlink()


def load_user_rules() -> RuleSet:
    """加载用户规则文件；无文件/空 → 内置默认规则集。

    GUI 脱敏用：用户规则覆盖/新增规则定义，列映射用默认 + 自动匹配。
    """
    defs = {name: _build_rule_def(name, raw) for name, raw in get_rule_defs().items()}
    specs = [RuleSpec(**m, optional=True) for m in DEFAULT_MAPPING]
    return RuleSet(defs=defs, specs=specs)


def rules_for_gui() -> list[dict[str, Any]]:
    """返回 GUI 展示的规则列表（含来源标注：内置/用户）。"""
    builtin = set(BUILTIN_RULE_DEFS.keys())
    defs = get_rule_defs()
    result = []
    for name, raw in sorted(defs.items()):
        result.append({
            "name": name,
            "version": str(raw.get("version", "1.0")),
            "match": raw.get("match", ""),
            "mask": raw.get("mask", ""),
            "pseudo": raw.get("pseudo", ""),
            "source": "内置" if name in builtin else "自定义",
            "default_disabled": bool(raw.get("default_disabled", False)),
        })
    return result
