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


def test_value_scan_id_card_in_text_masked():
    """值内含身份证（非整值）走格内扫描脱敏。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({"备注": ["身份证 110101199003077777", "正常"]})
    masked, count = apply_rules(df, rs, None)
    assert "110101199003077777" not in masked["备注"].to_list()[0]
    assert "正常" == masked["备注"].to_list()[1]
    assert count == 1


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


def test_in_cell_email_and_ip():
    """格内扫描：句子里的邮箱/IP 被替换，周围文字保留。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({
        "正文": [
            "申请人：张伟，联系邮箱 alice@corp.example，请审批。",
            "故障主机 IP 为 10.1.2.3，值班。",
        ]
    })
    masked, count = apply_rules(df, rs, None)
    rows = masked["正文"].to_list()
    assert "alice@corp.example" not in rows[0]
    assert "a***@corp.example" in rows[0]
    assert "申请人：张伟" in rows[0]  # 无清单不扫句中人名
    assert "10.1.2.3" not in rows[1]
    assert "*.*.*.*" in rows[1]
    assert count == 2


def test_in_cell_person_list_substring():
    """有人员清单：句中清单人名被替换。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({"正文": ["故障主机值班 李娜。", "普通人名赵磊在句中"]})
    masked, count = apply_rules(df, rs, None, person_list={"李娜"})
    rows = masked["正文"].to_list()
    assert "李娜" not in rows[0]
    assert "李*" in rows[0]
    assert "赵磊" in rows[1]  # 清单外，不启发式扫句中
    assert count == 1


def test_mapped_email_column_skips_non_email():
    """列名命中 email 但值不是邮箱 → 不套模板（无 / 策划部）。"""
    from maskit.rules.defs import RuleSpec

    rs = load_ruleset()
    custom = RuleSet(
        defs=rs.defs,
        specs=[RuleSpec(column="备注邮箱", rule="email", strategy="mask")],
    )
    df = pl.DataFrame({"备注邮箱": ["alice@corp.example", "无", "策划部"]})
    masked, count = apply_rules(df, custom, None)
    rows = masked["备注邮箱"].to_list()
    assert "alice@corp.example" not in rows[0]
    assert rows[1] == "无"
    assert rows[2] == "策划部"
    assert count == 1


def test_in_cell_mixed_id_and_name_with_list():
    """格内同时有身份证和清单人名。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({
        "正文": ["身份证 110101199003077777 复印件已归档（经办 司马光）。"]
    })
    masked, count = apply_rules(df, rs, None, person_list={"司马光"})
    text = masked["正文"].to_list()[0]
    assert "110101199003077777" not in text
    assert "司马光" not in text
    assert count == 1


def test_catchall_company_skips_department():
    """YAML 显式 company 列：财务部不套模板，亚玛芬体育仍套。"""
    from maskit.rules.defs import RuleSpec

    rs = load_ruleset()
    custom = RuleSet(
        defs=rs.defs,
        specs=[RuleSpec(column="单位", rule="company", strategy="mask")],
    )
    df = pl.DataFrame({"单位": ["财务部", "亚玛芬体育", "办公室"]})
    masked, count = apply_rules(df, custom, None)
    rows = masked["单位"].to_list()
    assert rows[0] == "财务部"
    assert rows[1] == "亚*"
    assert rows[2] == "办公室"
    assert count == 1


def test_mapped_app_version_skips_date():
    """列名版本：日期形态 2024.1.1 不套模板，v1.2.3 仍套。"""
    from maskit.rules.defs import RuleSpec

    rs = load_ruleset()
    custom = RuleSet(
        defs=rs.defs,
        specs=[RuleSpec(column="版本", rule="app_version", strategy="mask")],
    )
    df = pl.DataFrame({"版本": ["2024.1.1", "v1.2.3", "1.2.3"]})
    masked, count = apply_rules(df, custom, None)
    rows = masked["版本"].to_list()
    assert rows[0] == "2024.1.1"
    assert rows[1] == "v1.*.*"
    assert rows[2] == "v1.*.*"
    assert count == 2


def test_person_list_no_substring_or_org_cut():
    """清单人名不切张伟达、不切东方不败工作室；双名粘连仍遮。"""
    rs = _empty_specs_ruleset()
    people = {"张伟", "李娜", "东方不败"}
    df = pl.DataFrame({
        "正文": [
            "选手张伟达获奖",
            "东方不败工作室来函",
            "张伟李娜均出席",
            "故障主机值班 李娜。",
        ]
    })
    masked, _count = apply_rules(df, rs, None, person_list=people)
    rows = masked["正文"].to_list()
    assert "张伟达" in rows[0]
    assert "东方不败工作室" in rows[1]
    assert "张*" in rows[2] and "李*" in rows[2]
    assert "李娜" not in rows[3]
    assert "李*" in rows[3]


def test_in_cell_ip_skips_version_lookalike():
    """格内 IP 不吃 v10.20.30.40，真 IP 仍遮。"""
    rs = _empty_specs_ruleset()
    df = pl.DataFrame({
        "正文": [
            "客户端 v10.20.30.40 发布",
            "故障主机 IP 为 10.1.2.3，值班。",
        ]
    })
    masked, count = apply_rules(df, rs, None)
    rows = masked["正文"].to_list()
    assert "v10.20.30.40" in rows[0]
    assert "10.1.2.3" not in rows[1]
    assert "*.*.*.*" in rows[1]
    assert count == 1


def test_in_cell_spaced_id_dashed_bank_fullwidth_email():
    """空格证号、横线卡号、全角邮箱走写法变体扫描。"""
    rs = _empty_specs_ruleset()
    fullwidth = "邮箱：ａｌｉｃｅ＠ｃｏｒｐ．ｅｘａｍｐｌｅ"
    df = pl.DataFrame({
        "正文": [
            "身份证 110101 19900307 7777",
            "卡号 6222-0212-3456-7890",
            fullwidth,
        ]
    })
    masked, count = apply_rules(df, rs, None)
    rows = masked["正文"].to_list()
    assert "110101199003077777" not in rows[0].replace(" ", "")
    assert "6222021234567890" not in "".join(ch for ch in rows[1] if ch.isdigit())
    assert "ａｌｉｃｅ" not in rows[2]
    assert count == 3
