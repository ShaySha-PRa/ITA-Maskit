"""规则集预验证测试：preview_dataframe + preview_ruleset_file。

核心保证：预验证与实际脱敏（apply_rules）命中一致。
"""
from __future__ import annotations

import polars as pl
import pytest

from maskit.preview import preview_ruleset_file
from maskit.rules.defs import RuleSet
from maskit.rules.engine import apply_rules, preview_dataframe
from maskit.rules.loader import load_ruleset


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "姓名": ["张伟", "李娜"],
            "手机号": ["13800000000", "13800000001"],
            "备注": ["普通", "普通"],
        }
    )


# --- preview_dataframe（引擎层） ---

def test_preview_dataframe_per_column():
    """每列统计：映射列命中规则、未映射敏感值走值级检测、普通列未命中。"""
    rs = load_ruleset()
    cols = preview_dataframe(_sample_df(), rs, None)
    by_name = {c["column"]: c for c in cols}

    # 姓名 → name 规则（自动列匹配），2/2
    assert by_name["姓名"]["rule"] == "name"
    assert by_name["姓名"]["hits"] == 2
    assert by_name["姓名"]["sample_before"] == "张伟"
    assert by_name["姓名"]["sample_after"] == "张*"
    # 手机号 → phone 规则，2/2
    assert by_name["手机号"]["rule"] == "phone"
    assert by_name["手机号"]["hits"] == 2
    # 备注 → 无规则命中
    assert by_name["备注"]["rule"] is None
    assert by_name["备注"]["hits"] == 0
    assert by_name["备注"]["total"] == 2


def test_preview_matches_apply_rules():
    """预验证命中总数 == 实际脱敏计数（同一 DataFrame、同一规则集）。

    实际脱敏走 _mask_dataframe（含可选列过滤 + 自动列匹配），
    预览应与它完全一致——保证「预览=实际」。
    """
    from maskit.io.csvio import _mask_dataframe

    rs = load_ruleset()
    _, actual = _mask_dataframe(_sample_df(), rs, None)
    preview_total = sum(c["hits"] for c in preview_dataframe(_sample_df(), rs, None))
    assert preview_total == actual


def test_preview_empty_df():
    """空 DataFrame → 每列 0 命中。"""
    rs = load_ruleset()
    df = pl.DataFrame({"姓名": []}, schema={"姓名": pl.Utf8})
    cols = preview_dataframe(df, rs, None)
    assert cols[0]["hits"] == 0
    assert cols[0]["total"] == 0


def test_preview_person_list():
    """人员清单：清单里的名字命中（精确匹配）。"""
    rs = load_ruleset()
    rs_empty = RuleSet(defs=rs.defs, specs=[])
    people = {"东方不败"}
    df = pl.DataFrame({"选手": ["东方不败", "普通"]})
    cols = preview_dataframe(df, rs_empty, None, person_list=people)
    by_name = {c["column"]: c for c in cols}
    assert by_name["选手"]["rule"] == "name"
    assert by_name["选手"]["hits"] == 1
    assert by_name["选手"]["sample_after"] == "东*"


def test_preview_whitespace_value_matches_engine():
    """带空格的姓名：预览样本与实际脱敏一致（值级检测 strip 后处理）。"""
    rs = load_ruleset()
    rs_empty = RuleSet(defs=rs.defs, specs=[])
    df = pl.DataFrame({"选手": [" 张伟 ", "普通"]})
    cols = preview_dataframe(df, rs_empty, None)
    masked, _ = apply_rules(df, rs_empty, None)
    by_name = {c["column"]: c for c in cols}
    assert by_name["选手"]["hits"] == 1
    assert masked["选手"].to_list()[0] == "张*"  # 实际脱敏对 strip 后处理
    assert by_name["选手"]["sample_after"] == "张*"


# --- preview_ruleset_file（文件层） ---

def test_preview_csv_file(tmp_path):
    """CSV 文件预验证。"""
    f = tmp_path / "in.csv"
    f.write_text("姓名,手机号,备注\n张伟,13800000000,普通\n李娜,13800000001,普通\n", encoding="utf-8")
    res = preview_ruleset_file(str(f), load_ruleset())
    assert res["format"] == "csv"
    assert res["total_hits"] == 4
    assert res["total_cells"] == 6
    assert len(res["sheets"]) == 1
    assert res["sheets"][0]["sheet"] is None


def test_preview_excel_multi_sheet(tmp_path):
    """Excel 多 sheet：每个 sheet 都预验证。"""
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    f = tmp_path / "multi.xlsx"
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "员工"
    ws1.append(["姓名", "手机号"])
    ws1.append(["张伟", "13800000000"])
    ws2 = wb.create_sheet("客户")
    ws2.append(["手机号", "备注"])
    ws2.append(["13800000002", "普通"])
    wb.save(str(f))

    res = preview_ruleset_file(str(f), load_ruleset())
    assert res["format"] == "xlsx"
    assert [s["sheet"] for s in res["sheets"]] == ["员工", "客户"]
    assert res["total_hits"] == 3  # 员工 2 + 客户 1
    assert res["total_cells"] == 4


def test_preview_missing_file(tmp_path):
    """文件不存在 → FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        preview_ruleset_file(str(tmp_path / "none.csv"), load_ruleset())


def test_preview_unsupported_format(tmp_path):
    """文本格式（无列）→ 报错提示。"""
    f = tmp_path / "note.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(ValueError, match="不支持"):
        preview_ruleset_file(str(f), load_ruleset())


def test_preview_empty_csv(tmp_path):
    """空 CSV → 无命中且不报错。"""
    f = tmp_path / "empty.csv"
    f.write_text("姓名\n", encoding="utf-8")  # 只有表头
    res = preview_ruleset_file(str(f), load_ruleset())
    assert res["total_hits"] == 0
    assert res["total_cells"] == 0
