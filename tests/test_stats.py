"""脱敏统计（MaskStats）与引擎计数测试。"""
import polars as pl

from maskit.rules.engine import apply_rules
from maskit.rules.loader import load_ruleset
from maskit.stats import MaskStats


def test_stats_add():
    """MaskStats 累加。"""
    s = MaskStats()
    s.add(processed=100, masked=30)
    s.add(processed=50, masked=10, files=1)
    assert s.processed == 150
    assert s.masked == 40
    assert s.files == 1


def test_stats_iadd():
    """MaskStats += 累加。"""
    a = MaskStats(processed=10, masked=5, files=2)
    b = MaskStats(processed=20, masked=8, files=1)
    a += b
    assert a.processed == 30
    assert a.masked == 13
    assert a.files == 3


def test_stats_masked_ratio():
    """脱敏占比。"""
    assert MaskStats().masked_ratio == 0.0
    assert MaskStats(processed=100, masked=25).masked_ratio == 0.25


def test_apply_rules_returns_count():
    """apply_rules 返回 (脱敏后df, 脱敏单元格数)。"""
    ruleset = load_ruleset()
    # 默认规则集含 8 列，测试 DataFrame 用全列
    df = pl.DataFrame(
        {
            "name": ["张伟", "李娜"],
            "email": ["a@b.com", "c@d.com"],
            "ip": ["10.1.2.3", "10.1.2.4"],
            "phone": ["13800000000", "13800000001"],
            "employee_id": ["EID-1001", "EID-1002"],
            "account": ["zhangsan", "lisi"],
            "company": ["亚玛芬体育", "MayAir"],
            "app_version": ["v1.2.3", "v2.0.0"],
        }
    )
    masked_df, count = apply_rules(df, ruleset, None)
    assert count == 16  # 8 列 × 2 行全被改
    assert masked_df["name"].to_list() == ["张*", "李*"]


def test_apply_rules_count_only_changed():
    """只统计实际改变的单元格（空值不计数）。"""
    ruleset = load_ruleset()
    df = pl.DataFrame(
        {
            "name": ["张伟", ""],
            "email": ["a@b.com", "c@d.com"],
            "ip": ["10.1.2.3", "10.1.2.4"],
            "phone": ["13800000000", "13800000001"],
            "employee_id": ["EID-1001", "EID-1002"],
            "account": ["zhangsan", "lisi"],
            "company": ["亚玛芬体育", "MayAir"],
            "app_version": ["v1.2.3", "v2.0.0"],
        }
    )
    # 空 name 不被改（_mask_single 返回空），所以少计 1
    masked_df, count = apply_rules(df, ruleset, None)
    assert masked_df["name"].to_list()[1] == ""  # 空值保持空
    assert count == 15  # 16 - 1（空 name 不计数）


# --- GUI 冒烟（offscreen，CI 无显示环境） ---

def test_gui_mainwindow_creates():
    """GUI 主窗口在 offscreen 平台可创建。"""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import sys

    from PyQt5.QtWidgets import QApplication

    from maskit.gui import MainWindow

    app = QApplication(sys.argv)
    win = MainWindow()
    assert win.windowTitle() == "ITA-Maskit 数据脱敏工具"
    assert "未选择文件" in win.file_label.text()
    win.close()
    app.quit()
