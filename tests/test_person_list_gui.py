"""人员清单在表格脱敏生效测试（方法一：人名词表）。"""

import polars as pl
import pytest

from maskit.io import mask_file
from maskit.rules.engine import _value_scan_single, apply_rules
from maskit.rules.loader import _build_rule_def, load_ruleset
from maskit.rules.name_company import load_person_list


@pytest.fixture
def people(tmp_path):
    """构造人员清单 CSV。"""
    csv = tmp_path / "people.csv"
    csv.write_text("name\n欧阳修\n司马光\n东方不败\n", encoding="utf-8")
    return load_person_list(csv)


def test_value_scan_uses_person_list(people):
    """清单里的名字（即使不在姓氏启发式）→ 脱敏。"""
    from maskit.rules.defs import RuleSet

    rs = load_ruleset()
    rs_empty = RuleSet(defs=rs.defs, specs=[])
    df = pl.DataFrame({"选手": ["欧阳修", "普通"]})
    masked, count = apply_rules(df, rs_empty, None, person_list=people)
    assert masked["选手"].to_list()[0] == "欧*"
    assert masked["选手"].to_list()[1] == "普通"
    assert count == 1


def test_person_list_prefers_over_heuristic(people):
    """清单优先：清单里的名字精确匹配。"""
    from maskit.rules.defs import RuleSet

    rs = load_ruleset()
    rs_empty = RuleSet(defs=rs.defs, specs=[])
    # 司马光在复姓启发式也识别，但东方不败靠清单
    df = pl.DataFrame({"选手": ["东方不败", "司马光"]})
    masked, count = apply_rules(df, rs_empty, None, person_list=people)
    assert masked["选手"].to_list()[0] == "东*"
    assert masked["选手"].to_list()[1] == "司*"
    assert count == 2


def test_csv_mask_with_person_list(people, tmp_path):
    """CSV 脱敏用人员清单：清单名字覆盖。"""
    src = tmp_path / "in.csv"
    src.write_text("选手\n欧阳修\n普通\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    details = {}
    mask_file(str(src), str(out), load_ruleset(), None, details=details, person_list=people)
    data = out.read_text(encoding="utf-8").strip().splitlines()
    assert data[1] == "欧*"
    assert data[2] == "普通"
    assert details["masked"] == 1


def test_person_list_no_false_positive(people):
    """清单外名字不因清单被脱敏（除非启发式命中）。"""
    from maskit.rules.defs import RuleSet

    rs = load_ruleset()
    rs_empty = RuleSet(defs=rs.defs, specs=[])
    # 「策划部」不在清单也不在启发式（非姓氏开头）→ 不脱敏
    df = pl.DataFrame({"字段": ["策划部", "张伟"]})
    masked, count = apply_rules(df, rs_empty, None, person_list=people)
    assert masked["字段"].to_list()[0] == "策划部"
    assert count == 1  # 张伟 通过启发式脱敏


def test_value_scan_single_with_person_list(people):
    """单值检测：清单命中。"""
    name_rule = _build_rule_def("name", {"match": ".+", "mask": "{first}*", "pseudo": "N"})
    out = _value_scan_single("东方不败", [], "mask", None, name_rule=name_rule, person_list=people)
    assert out["changed"] == 1
    assert out["masked_value"] == "东*"


def test_value_scan_single_without_person_list():
    """无清单时：不复姓启发式外的名字不脱敏。"""
    name_rule = _build_rule_def("name", {"match": ".+", "mask": "{first}*", "pseudo": "N"})
    out = _value_scan_single("东方不败", [], "mask", None, name_rule=name_rule, person_list=None)
    # 东方 在复姓表 → 启发式命中（东方是复姓）
    assert out["changed"] == 1
