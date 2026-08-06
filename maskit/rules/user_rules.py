"""用户规则文件管理（GUI 规则可视化编辑 + 多规则集）。

多套规则集存于 ~/.maskit/rulesets/{name}.yaml，支持：
- 保存一套规则 / 切换当前规则集 / 导入导出 / 删除
- 「内置默认」作为不可修改的默认规则集
- 旧版 user_rules.yaml 首次运行自动迁移为「我的规则」规则集
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from maskit.rules.defs import BUILTIN_RULE_DEFS, RuleSet, RuleSpec
from maskit.rules.loader import DEFAULT_MAPPING, _build_rule_def

# 用户规则集目录与当前规则集标记
USER_HOME = Path.home() / ".maskit"
RULESETS_DIR = USER_HOME / "rulesets"
CURRENT_RS_FILE = USER_HOME / "current_ruleset"

# 内置默认规则集名（特殊，不可修改/删除）
BUILTIN_RS = "内置默认"
# 旧版 user_rules.yaml 迁移后的规则集名
LEGACY_RS = "我的规则"

# 规则定义必填字段
_REQUIRED_FIELDS = ("match", "mask", "pseudo")


def _base_dir() -> Path:
    """规则集基础目录（可用 MASKIT_RULESETS_DIR 覆盖，测试用）。"""
    override = os.environ.get("MASKIT_RULESETS_DIR")
    if override:
        return Path(override)
    return RULESETS_DIR


def _current_file() -> Path:
    override = os.environ.get("MASKIT_CURRENT_RS")
    if override:
        return Path(override)
    return CURRENT_RS_FILE


def _migrate_legacy():
    """迁移旧版 user_rules.yaml → 「我的规则」规则集（首次运行）。"""
    legacy = os.environ.get("MASKIT_USER_RULES")
    legacy_path = Path(legacy) if legacy else (USER_HOME / "user_rules.yaml")
    if not legacy_path.exists():
        return
    data = {}
    try:
        data = yaml.safe_load(legacy_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        data = {}
    defs = data.get("rule_defs") or {}
    if defs:
        rs_path = _base_dir() / f"{LEGACY_RS}.yaml"
        rs_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(rs_path, {"rule_defs": defs})
    # 迁移后改名旧文件，避免重复迁移
    try:
        legacy_path.rename(legacy_path.with_suffix(".bak"))
    except OSError:
        pass


def _atomic_write(path: Path, data: dict) -> None:
    """原子写 YAML（temp + rename）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
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


# --- 规则定义加载/校验 ---

def _load_defs_from_file(path: Path) -> dict[str, dict[str, Any]]:
    """从规则集文件读 rule_defs。"""
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return {name: dict(raw) for name, raw in (data.get("rule_defs") or {}).items()}


def get_rule_defs() -> dict[str, dict[str, Any]]:
    """返回当前生效规则定义（内置 + 当前规则集覆盖/新增）。

    兼容旧调用：读当前规则集（若无，则内置）。
    """
    _migrate_legacy()
    return _defs_for_ruleset(get_current_ruleset())


def _defs_for_ruleset(name: str) -> dict[str, dict[str, Any]]:
    """返回某规则集的完整定义（内置 + 该规则集覆盖/新增）。"""
    defs = {n: dict(r) for n, r in BUILTIN_RULE_DEFS.items()}
    if name == BUILTIN_RS:
        return defs
    rs_path = _base_dir() / f"{name}.yaml"
    for rname, raw in _load_defs_from_file(rs_path).items():
        defs[rname] = dict(raw)
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


# --- 规则集 CRUD ---

def list_rulesets() -> list[str]:
    """列出所有规则集名（含「内置默认」，不含 .yaml 后缀）。"""
    _migrate_legacy()
    names = [BUILTIN_RS]
    base = _base_dir()
    if base.exists():
        for f in sorted(base.glob("*.yaml")):
            names.append(f.stem)
    return names


def save_ruleset(name: str, defs: dict[str, dict[str, Any]]) -> None:
    """保存一套规则集到 rulesets/{name}.yaml（原子写）。

    - 校验所有规则
    - 内置默认不可保存（它是只读的）
    """
    name = name.strip()
    if not name:
        raise ValueError("规则集名称不能为空")
    if name == BUILTIN_RS:
        raise ValueError("不能修改「内置默认」规则集")
    for rname, raw in defs.items():
        validate_rule_def(rname, raw)
    _atomic_write(_base_dir() / f"{name}.yaml", {"rule_defs": defs})


def load_ruleset(name: str) -> RuleSet:
    """加载指定规则集为 RuleSet；'内置默认' → 内置规则。

    列映射用默认 + 自动匹配（脱敏时）。
    """
    defs = {n: _build_rule_def(n, r) for n, r in _defs_for_ruleset(name).items()}
    specs = [RuleSpec(**m, optional=True) for m in DEFAULT_MAPPING]
    return RuleSet(defs=defs, specs=specs)


def ruleset_info(name: str) -> dict:
    """返回规则集信息：规则数、自定义规则数。"""
    defs = _defs_for_ruleset(name)
    builtin = set(BUILTIN_RULE_DEFS.keys())
    custom = [n for n in defs if n not in builtin]
    return {
        "name": name,
        "rule_count": len(defs),
        "custom_count": len(custom),
        "custom_rules": custom,
    }


def get_current_ruleset() -> str:
    """返回当前生效规则集名（默认「内置默认」）。"""
    path = _current_file()
    if path.exists():
        name = path.read_text(encoding="utf-8").strip()
        if name in list_rulesets():
            return name
    return BUILTIN_RS


def set_current_ruleset(name: str) -> None:
    """设置当前生效规则集。"""
    if name not in list_rulesets():
        raise ValueError(f"规则集 {name!r} 不存在")
    _current_file().parent.mkdir(parents=True, exist_ok=True)
    _current_file().write_text(name, encoding="utf-8")


def delete_ruleset(name: str) -> None:
    """删除一套规则集（不能删内置默认/当前生效的）。"""
    if name == BUILTIN_RS:
        raise ValueError("不能删除「内置默认」规则集")
    if name == get_current_ruleset():
        raise ValueError("不能删除当前生效的规则集，请先切换到其它规则集")
    path = _base_dir() / f"{name}.yaml"
    if path.exists():
        path.unlink()


def export_ruleset(name: str, to_path: str | Path) -> None:
    """导出规则集到指定文件（.yaml）。"""
    defs = _defs_for_ruleset(name)
    _atomic_write(Path(to_path), {"rule_defs": defs})


def import_ruleset(from_path: str | Path, name: str | None = None) -> str:
    """从文件导入规则集，返回导入的规则集名。

    - 校验文件内容（rule_defs）
    - name 缺省 → 用文件名（去 .yaml）
    - 导入后自动设为当前规则集
    """
    path = Path(from_path)
    if not path.exists():
        raise FileNotFoundError(f"规则文件不存在: {path}")
    defs = _load_defs_from_file(path)
    if not defs:
        raise ValueError(f"文件无有效规则: {path}")
    for rname, raw in defs.items():
        validate_rule_def(rname, raw)
    rs_name = name or path.stem
    save_ruleset(rs_name, defs)
    set_current_ruleset(rs_name)
    return rs_name


# --- 兼容旧接口 ---

def user_rules_path() -> Path:
    """旧接口：返回默认用户规则文件路径。"""
    return USER_HOME / "user_rules.yaml"


def save_user_rules(defs: dict[str, dict[str, Any]]) -> None:
    """旧接口：保存到「我的规则」规则集（即当前规则集）。"""
    save_ruleset(get_current_ruleset(), defs)


def delete_user_rules() -> None:
    """旧接口：删除用户规则文件（恢复内置默认）。"""
    path = user_rules_path()
    if path.exists():
        path.unlink()


def load_user_rules() -> RuleSet:
    """旧接口：加载当前规则集（脱敏用）。"""
    return load_ruleset(get_current_ruleset())


def rules_for_gui() -> list[dict[str, Any]]:
    """返回当前规则集的规则列表（含来源标注 + 描述）。"""
    builtin = set(BUILTIN_RULE_DEFS.keys())
    defs = _defs_for_ruleset(get_current_ruleset())
    result = []
    for name, raw in sorted(defs.items()):
        result.append({
            "name": name,
            "version": str(raw.get("version", "1.0")),
            "match": raw.get("match", ""),
            "mask": raw.get("mask", ""),
            "pseudo": raw.get("pseudo", ""),
            "description": raw.get("description", ""),
            "source": "内置" if name in builtin else "自定义",
            "default_disabled": bool(raw.get("default_disabled", False)),
        })
    return result
