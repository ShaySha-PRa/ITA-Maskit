"""用户规则文件管理测试。"""

import pytest

from maskit.rules.user_rules import (
    delete_user_rules,
    get_rule_defs,
    load_user_rules,
    rules_for_gui,
    save_user_rules,
    user_rules_path,
    validate_rule_def,
)


@pytest.fixture
def user_rules(tmp_path, monkeypatch):
    """隔离用户规则文件到临时目录。"""
    path = tmp_path / "user_rules.yaml"
    monkeypatch.setenv("MASKIT_USER_RULES", str(path))
    return path


def test_default_rules(user_rules):
    """无用户文件 → 内置规则。"""
    defs = get_rule_defs()
    assert "name" in defs
    assert "id_card" in defs
    assert "bank_card" in defs
    assert len(defs) >= 10


def test_save_and_load_custom_rule(user_rules):
    """保存自定义规则 → 重新加载生效。"""
    defs = get_rule_defs()
    defs["车牌号"] = {
        "version": "1.0",
        "match": r"^[京津沪渝冀豫云辽黑湘皖新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-Z][A-Z0-9]{5,6}$",
        "mask": "{first}*",
        "pseudo": "PL-{hash:8}",
    }
    save_user_rules(defs)
    loaded = get_rule_defs()
    assert "车牌号" in loaded
    rs = load_user_rules()
    assert "车牌号" in rs.defs


def test_validate_missing_fields(user_rules):
    """缺字段 → 报错。"""
    with pytest.raises(ValueError, match="缺少字段"):
        validate_rule_def("bad", {"match": r".+", "mask": "{first}*"})


def test_validate_bad_regex(user_rules):
    """非法正则 → 报错。"""
    with pytest.raises(ValueError, match="正则非法"):
        validate_rule_def("bad", {"match": "([", "mask": "{first}*", "pseudo": "X"})


def test_validate_empty_name(user_rules):
    """空规则名 → 报错。"""
    with pytest.raises(ValueError, match="不能为空"):
        validate_rule_def("", {"match": r".+", "mask": "{first}*", "pseudo": "X"})


def test_delete_user_rules(user_rules):
    """删除用户规则 → 恢复内置。"""
    defs = get_rule_defs()
    defs["自定义规则"] = {"version": "1.0", "match": r".+", "mask": "{first}*", "pseudo": "X"}
    save_user_rules(defs)
    assert "自定义规则" in get_rule_defs()
    delete_user_rules()
    assert "自定义规则" not in get_rule_defs()


def test_rules_for_gui_source(user_rules):
    """GUI 列表标注来源。"""
    rules = rules_for_gui()
    sources = {r["source"] for r in rules}
    assert "内置" in sources


def test_user_rules_path_default(monkeypatch):
    """默认路径 ~/.maskit/user_rules.yaml。"""
    monkeypatch.delenv("MASKIT_USER_RULES", raising=False)
    assert str(user_rules_path()).endswith("user_rules.yaml")


def test_custom_rule_masks_in_pipeline(user_rules):
    """自定义规则在脱敏流程中生效。"""
    import polars as pl

    from maskit.rules.defs import RuleSet, RuleSpec
    from maskit.rules.engine import apply_rules

    defs = get_rule_defs()
    defs["手机号"] = {
        "version": "1.0",
        "match": r"^1\d{10}$",
        "mask": "{head:3}****{tail:4}",
        "pseudo": "{digits}",
    }
    save_user_rules(defs)

    # 用用户规则 + 显式映射测试
    from maskit.rules.loader import _build_rule_def

    rule = _build_rule_def("手机号", defs["手机号"])
    df = pl.DataFrame({"phone": ["13800000000", "x"]})
    custom_rs = RuleSet(defs={"手机号": rule}, specs=[RuleSpec(column="phone", rule="手机号", strategy="mask")])
    masked, _ = apply_rules(df, custom_rs, None)
    assert masked["phone"].to_list()[0] == "138****0000"
