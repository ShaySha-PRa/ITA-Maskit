"""规则集管理测试：多套规则/切换/导入导出/删除。"""
import pytest

from maskit.rules.defs import BUILTIN_RULE_DEFS
from maskit.rules.user_rules import (
    BUILTIN_RS,
    delete_ruleset,
    export_ruleset,
    get_current_ruleset,
    import_ruleset,
    list_rulesets,
    load_ruleset,
    save_ruleset,
    set_current_ruleset,
)


@pytest.fixture
def rulesets_env(tmp_path, monkeypatch):
    """隔离规则集目录 + 当前规则集。"""
    monkeypatch.setenv("MASKIT_RULESETS_DIR", str(tmp_path / "rulesets"))
    monkeypatch.setenv("MASKIT_CURRENT_RS", str(tmp_path / "current"))
    return tmp_path


def _base_defs():
    return {n: dict(r) for n, r in BUILTIN_RULE_DEFS.items()}


def test_list_rulesets_default(rulesets_env):
    """默认只有「内置默认」。"""
    assert list_rulesets() == [BUILTIN_RS]


def test_save_list_load_ruleset(rulesets_env):
    """保存 → 列表出现 → 加载生效。"""
    defs = _base_defs()
    defs["车牌号"] = {
        "version": "1.0",
        "match": r"^[京津沪][A-Z]\d{5}$",
        "mask": "{first}*",
        "pseudo": "PL-{hash:8}",
        "description": "车牌号",
    }
    save_ruleset("2026审计", defs)
    assert "2026审计" in list_rulesets()
    rs = load_ruleset("2026审计")
    assert "车牌号" in rs.defs


def test_current_ruleset_default_and_switch(rulesets_env):
    """当前规则集：默认内置，可切换。"""
    assert get_current_ruleset() == BUILTIN_RS
    save_ruleset("测试集", _base_defs())
    set_current_ruleset("测试集")
    assert get_current_ruleset() == "测试集"


def test_cannot_modify_builtin(rulesets_env):
    """内置默认不可修改。"""
    with pytest.raises(ValueError, match="内置默认"):
        save_ruleset(BUILTIN_RS, _base_defs())


def test_export_import_ruleset(rulesets_env, tmp_path):
    """导出 → 导入 → 内容一致 + 自动设为当前。"""
    defs = _base_defs()
    defs["自定义"] = {"version": "1.0", "match": r"^\d{5}$", "mask": "{first}*", "pseudo": "X-{hash:8}"}
    save_ruleset("原规则", defs)

    exp = tmp_path / "export.yaml"
    export_ruleset("原规则", exp)
    assert exp.exists()

    # 切到内置，然后导入
    set_current_ruleset(BUILTIN_RS)
    name = import_ruleset(exp, "导入规则")
    assert name == "导入规则"
    assert get_current_ruleset() == "导入规则"
    rs = load_ruleset("导入规则")
    assert "自定义" in rs.defs


def test_import_invalid_file(rulesets_env, tmp_path):
    """导入非法文件 → 报错。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text("rule_defs:\n  x:\n    match: '[['\n", encoding="utf-8")
    with pytest.raises(ValueError):
        import_ruleset(bad)


def test_delete_ruleset(rulesets_env):
    """删除规则集：先切走再删。"""
    save_ruleset("待删", _base_defs())
    set_current_ruleset("待删")
    # 不能删当前生效的
    with pytest.raises(ValueError, match="当前生效"):
        delete_ruleset("待删")
    set_current_ruleset(BUILTIN_RS)
    delete_ruleset("待删")
    assert "待删" not in list_rulesets()


def test_delete_builtin_forbidden(rulesets_env):
    """不能删除内置默认。"""
    with pytest.raises(ValueError, match="内置默认"):
        delete_ruleset(BUILTIN_RS)


def test_ruleset_isolation(rulesets_env):
    """不同规则集互不影响。"""
    defs_a = _base_defs()
    defs_a["规则A专属"] = {"version": "1.0", "match": r"^A$", "mask": "*", "pseudo": "A"}
    defs_b = _base_defs()
    defs_b["规则B专属"] = {"version": "1.0", "match": r"^B$", "mask": "*", "pseudo": "B"}
    save_ruleset("集合A", defs_a)
    save_ruleset("集合B", defs_b)

    rs_a = load_ruleset("集合A")
    rs_b = load_ruleset("集合B")
    assert "规则A专属" in rs_a.defs
    assert "规则A专属" not in rs_b.defs
    assert "规则B专属" in rs_b.defs
    assert "规则B专属" not in rs_a.defs
