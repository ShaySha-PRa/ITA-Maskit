"""列名自动匹配测试。"""
from maskit.rules.matcher import auto_match_columns, auto_match_specs_for


def test_match_chinese_name_column():
    """中文列名自动匹配。"""
    specs = auto_match_columns(["姓名", "签约主体", "联系电话"])
    mapping = {s.column: s.rule for s in specs}
    assert mapping["姓名"] == "name"
    assert mapping["签约主体"] == "company"
    assert mapping["联系电话"] == "phone"


def test_match_english_columns():
    """英文列名自动匹配。"""
    specs = auto_match_columns(["name", "email", "ip", "phone", "company"])
    mapping = {s.column: s.rule for s in specs}
    assert mapping["name"] == "name"
    assert mapping["email"] == "email"
    assert mapping["ip"] == "ip"
    assert mapping["phone"] == "phone"
    assert mapping["company"] == "company"


def test_unmatched_columns_passthrough():
    """无匹配列不生成 spec（原样透传）。"""
    specs = auto_match_columns(["期间", "岗位", "队伍ID"])
    assert specs == []


def test_longest_keyword_wins():
    """最长关键词优先（「员工姓名」→ name 非 employee_id）。"""
    specs = auto_match_columns(["员工姓名"])
    assert specs[0].rule == "name"


def test_id_card_matches():
    """身份证列自动匹配。"""
    specs = auto_match_columns(["身份证号", "身份证号码"])
    mapping = {s.column: s.rule for s in specs}
    assert mapping["身份证号"] == "id_card"
    assert mapping["身份证号码"] == "id_card"


def test_serializable_specs():
    """返回可序列化 dict。"""
    out = auto_match_specs_for(["姓名"])
    assert out == [{"column": "姓名", "rule": "name", "strategy": "mask"}]
