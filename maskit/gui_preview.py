"""规则集预验证 GUI：后台预演 + 结果对话框。

「预验证」不产出文件，只预览：哪些列会被脱敏、命中多少、
改了什么样例，以及哪些列规则没命中（提示规则可能要调整）。
"""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class PreviewWorker(QThread):
    """后台预验证线程：逐个文件预演，避免卡 UI。"""

    file_done = pyqtSignal(int, dict)  # (索引, 结果 dict)
    all_done = pyqtSignal()

    def __init__(self, files: list[str], ruleset, pepper=None, person_list=None):
        super().__init__()
        self.files = files
        self.ruleset = ruleset
        self.pepper = pepper
        self.person_list = person_list

    def run(self):
        from maskit.preview import preview_ruleset_file

        for i, f in enumerate(self.files):
            try:
                result = preview_ruleset_file(
                    f, self.ruleset, self.pepper, self.person_list
                )
                self.file_done.emit(i, result)
            except Exception as exc:  # noqa: BLE001 — GUI 层捕获所有异常显示
                self.file_done.emit(i, {"path": f, "error": str(exc)})
        self.all_done.emit()


class RulesPreviewDialog(QDialog):
    """预验证结果对话框：表格展示各列命中情况 + 汇总。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("规则集预验证结果")
        self.resize(920, 520)

        layout = QVBoxLayout(self)
        self.summary = QLabel("")
        self.summary.setStyleSheet("font-weight: bold; padding: 2px;")
        layout.addWidget(self.summary)

        legend = QLabel(
            "🟩 绿=将脱敏 · 🟨 黄=规则未命中该列（可能需调整规则） · 🟥 红=预验证出错"
        )
        legend.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(legend)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["文件", "Sheet", "列", "命中规则", "策略", "命中/可检测", "命中率", "改前 → 改后"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox()
        buttons.addButton("关闭", QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def populate(self, results: list[dict], skipped_count: int = 0):
        """填充结果表格。results 为 per-file 预验证结果 dict。"""
        from maskit.io import is_image_format, is_text_format

        total_hits = 0
        total_cells = 0
        previewed = 0
        rows_data: list[tuple[list[str], str]] = []  # (单元格, 行类别)

        for res in results:
            if "error" in res:
                rows_data.append(([Path(res["path"]).name, "", "", "", "错误", "", "", res["error"]], "error"))
                continue
            p = Path(res["path"]).name
            previewed += 1
            for sheet in res.get("sheets", []):
                for col in sheet.get("columns", []):
                    total_cells += col["total"]
                    total_hits += col["hits"]
                    sample = (
                        f"{col['sample_before']} → {col['sample_after']}"
                        if col["sample_before"] is not None else ""
                    )
                    ratio = f"{col['ratio']:.0%}" if col["ratio"] else "0%"
                    kind = "hit" if col["hits"] > 0 else ("no_hit" if col["total"] > 0 else "empty")
                    rows_data.append((
                        [p, sheet.get("sheet") or "", col["column"], col["rule"] or "",
                         col["strategy"] or "", f"{col['hits']}/{col['total']}",
                         ratio, sample],
                        kind,
                    ))

        skip_note = ""
        if skipped_count:
            skip_note = f" · {skipped_count} 个文本/图片格式跳过（无列可预验证）"
        self.summary.setText(
            f"共 {previewed} 个文件预验证 · 将脱敏 {total_hits} 个单元格 / 可检测 {total_cells} 个{skip_note}"
        )

        self.table.setRowCount(len(rows_data))
        colors = {
            "hit": QColor(232, 245, 233),     # 浅绿
            "no_hit": QColor(255, 249, 219),  # 浅黄
            "empty": QColor(255, 255, 255),
            "error": QColor(253, 237, 237),   # 浅红
        }
        for r, (cells, kind) in enumerate(rows_data):
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(colors[kind])
                self.table.setItem(r, c, item)


def _is_previewable(path: str) -> bool:
    """是否可预验证（表格格式）。"""
    return Path(path).suffix.lower() in {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson"}
