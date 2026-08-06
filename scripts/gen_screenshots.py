"""生成 README 用的 GUI 界面演示截图（离屏渲染，无需显示器）。

用法：python scripts/gen_screenshots.py
产出：docs/screenshots/{main,rules,preview}.png

原理：QT_QPA_PLATFORM=offscreen 无显示器渲染，用 QWidget.grab() 把
真实窗口（主界面 / 规则管理 / 预验证结果）存成 PNG，配样例数据展示。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "assets" / "screenshots"

# 直接运行脚本时（python scripts/gen_screenshots.py），
# sys.path[0] 是 scripts/，需把项目根加进来才能 import maskit
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _sample_files(tmp: Path) -> list[str]:
    """生成样例数据文件（真实存在的文件，供主界面文件列表展示）。"""
    import openpyxl

    # CSV：员工信息表
    csv = tmp / "员工信息表.csv"
    csv.write_text(
        "姓名,手机号,身份证号,部门\n"
        "张伟,13800000000,110101199003077777,财务部\n"
        "李娜,13800000001,310104198512120022,人力资源部\n"
        "王芳,13912345678,440305199508300033,审计部\n",
        encoding="utf-8",
    )
    # Excel：客户联系表（多 sheet）
    xlsx = tmp / "客户联系表.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "客户"
    ws.append(["客户姓名", "手机号", "邮箱"])
    ws.append(["欧阳修", "13611112222", "ouyang@corp.com"])
    ws.append(["司马光", "13633334444", "sima@corp.com"])
    ws2 = wb.create_sheet("备注")
    ws2.append(["说明", "金额"])
    ws2.append(["常规往来", "12000"])
    wb.save(str(xlsx))
    # JSONL：供应商清单
    jsonl = tmp / "供应商清单.jsonl"
    jsonl.write_text(
        '{"供应商名称": "亚玛芬体育", "联系人": "林志强", "联系电话": "15800001111"}\n'
        '{"供应商名称": "MayAir", "联系人": "陈晓东", "联系电话": "15800002222"}\n',
        encoding="utf-8",
    )
    return [str(csv), str(xlsx), str(jsonl)]


def _main_window(app, files: list[str]) -> Path:
    """主界面：文件列表 + 结果表（模拟一次脱敏完成后的状态）。"""
    from maskit.gui import MainWindow

    win = MainWindow()
    win.resize(760, 640)
    win._add_files(files)  # 填充文件列表
    # 模拟脱敏完成：结果表 + 统计
    results = [
        (0, "员工信息表.csv (1 sheet, 1 sheet含脱敏)", "成功", "输出/员工信息表_masked.csv"),
        (1, "客户联系表.xlsx (2 sheets, 2 sheets含脱敏)", "成功", "输出/客户联系表_masked.xlsx"),
        (2, "供应商清单.jsonl", "成功", "输出/供应商清单_masked.jsonl"),
    ]
    for idx, name, status, out in results:
        win._on_file_done(idx, name, status, out)
    win._on_stats(processed=7, masked=7)
    win.show()
    app.processEvents()
    return _save(win, "main")


def _rules_manager(app) -> Path:
    """规则管理：可视化规则列表 + AI 生成（含上传规定文档）。"""
    from maskit.gui_rules import RulesManagerDialog

    dlg = RulesManagerDialog()
    dlg.resize(820, 560)
    dlg.show()
    app.processEvents()
    return _save(dlg, "rules")


def _preview(app) -> Path:
    """预验证结果：命中绿 / 未命中黄 / 出错红。"""
    from maskit.gui_preview import RulesPreviewDialog

    dlg = RulesPreviewDialog()
    results = [
        {
            "path": "C:/数据/员工信息表.xlsx", "format": "xlsx",
            "sheets": [
                {
                    "sheet": "员工", "columns": [
                        {"column": "姓名", "rule": "name", "strategy": "mask",
                         "hits": 2, "total": 2, "ratio": 1.0,
                         "sample_before": "张伟", "sample_after": "张*"},
                        {"column": "手机号", "rule": "phone", "strategy": "mask",
                         "hits": 2, "total": 2, "ratio": 1.0,
                         "sample_before": "13800000000", "sample_after": "138****0000"},
                        {"column": "身份证号", "rule": "id_card", "strategy": "mask",
                         "hits": 2, "total": 2, "ratio": 1.0,
                         "sample_before": "110101199003077777", "sample_after": "110101****7777"},
                        {"column": "部门", "rule": None, "strategy": None,
                         "hits": 0, "total": 2, "ratio": 0.0,
                         "sample_before": None, "sample_after": None},
                    ],
                },
            ],
            "total_hits": 6, "total_cells": 8,
        },
        {
            "path": "C:/数据/客户联系表.xlsx", "format": "xlsx",
            "sheets": [
                {
                    "sheet": "客户", "columns": [
                        {"column": "客户姓名", "rule": "name", "strategy": "mask",
                         "hits": 2, "total": 2, "ratio": 1.0,
                         "sample_before": "欧阳修", "sample_after": "欧*"},
                        {"column": "手机号", "rule": "phone", "strategy": "mask",
                         "hits": 2, "total": 2, "ratio": 1.0,
                         "sample_before": "13611112222", "sample_after": "136****2222"},
                    ],
                },
            ],
            "total_hits": 4, "total_cells": 4,
        },
        {
            "path": "C:/数据/坏文件.csv", "error": "无法读取输入文件",
        },
    ]
    dlg.populate(results, skipped_count=1)
    dlg.resize(980, 520)
    dlg.show()
    app.processEvents()
    return _save(dlg, "preview")


def _save(widget, name: str) -> Path:
    _OUT.mkdir(parents=True, exist_ok=True)
    path = _OUT / f"{name}.png"
    widget.grab().save(str(path))
    print(f"已生成 {path}")
    return path


def main() -> None:
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    app.setStyle("Fusion")

    with tempfile.TemporaryDirectory() as td:
        files = _sample_files(Path(td))
        _main_window(app, files)
    _rules_manager(app)
    _preview(app)


if __name__ == "__main__":
    main()
