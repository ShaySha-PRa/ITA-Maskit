"""值级敏感检测测试：补列名漏检。"""
import polars as pl

from maskit.rules.defs import RuleSet
from maskit.rules.engine import _value_scan_single, apply_rules
from maskit.rules.loader import load_ruleset


def _empty_specs_ruleset():
    """规则集：只有 defs 无 specs（纯值级检测）。"""
    rs = load_ruleset()
    return RuleSet(defs=rs.defs, specs=[])


def test_value_scan_id_card_full_value():
    """整值身份证被检测脱敏（值整体匹配）。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({"证件": ["110101199003077777", "普通文本"]})
    masked, count = apply_rules(df, rs, None)
    assert "110101199003077777" not in masked["证件"].to_list()[0]
    assert count == 1


def test_value_scan_id_card_in_text_kept():
    """值内含身份证（非整值）不脱敏（防误伤，整值检测）。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({"备注": ["身份证 110101199003077777", "正常"]})
    masked, count = apply_rules(df, rs, None)
    # 值内含不整值匹配 → 保留（防误伤普通文本）
    assert masked["备注"].to_list()[0] == "身份证 110101199003077777"
    assert count == 0


def test_value_scan_email():
    """未匹配列的邮箱（整值）被检测。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({"说明": ["a@b.com", "随便"]})
    masked, count = apply_rules(df, rs, None)
    assert "a@b.com" not in masked["说明"].to_list()[0]
    assert count == 1


def test_value_scan_no_false_positive_dates():
    """日期/小数/公式不被值检测误伤。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({"金额": ["2.5", "2024.1.1", "=SUM(H13:H17)", "100"]})
    masked, count = apply_rules(df, rs, None)
    assert masked["金额"].to_list() == ["2.5", "2024.1.1", "=SUM(H13:H17)", "100"]
    assert count == 0


def test_value_scan_no_false_positive_chinese():
    """中文名/普通文字不被值检测误伤。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({"备注": ["张伟负责审批", "采购流程", "2026年度"]})
    masked, count = apply_rules(df, rs, None)
    assert masked["备注"].to_list() == ["张伟负责审批", "采购流程", "2026年度"]
    assert count == 0


def test_value_scan_matched_col_not_duplicated():
    """已匹配列不重复值检测。"""
    rs = load_ruleset()
    # 用显式 specs：name 列匹配
    from maskit.rules.defs import RuleSpec

    custom = RuleSet(defs=rs.defs, specs=[RuleSpec(column="姓名", rule="name", strategy="mask")])
    df = pl.DataFrame({"姓名": ["张伟", "李娜"], "备注": ["110101199003077777", "x"]})
    masked, count = apply_rules(df, custom, None)
    assert masked["姓名"].to_list() == ["张*", "李*"]  # 列名匹配
    assert "110101199003077777" not in masked["备注"].to_list()[0]  # 值检测
    assert count == 3  # 2 姓名 + 1 身份证


def test_value_scan_can_disable():
    """value_scan=False 时不做值检测。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({"备注": ["110101199003077777"]})
    masked, count = apply_rules(df, rs, None, value_scan=False)
    assert masked["备注"].to_list()[0] == "110101199003077777"
    assert count == 0


def test_value_scan_single():
    """单值检测函数。"""
    rs = load_ruleset()
    from maskit.rules.engine import _build_value_scan_regexes

    regexes = _build_value_scan_regexes(rs)
    out = _value_scan_single("110101199003077777", regexes, "mask", None)
    assert out["changed"] == 1
    out2 = _value_scan_single("普通文本", regexes, "mask", None)
    assert out2["changed"] == 0
