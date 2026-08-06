"""ITA-Maskit 桌面 GUI（PyQt5）。

面向不懂代码的 IT 审计人员：拖拽/选择文件 → 点按钮脱敏 → 查看/保存结果。
实时显示：处理数据数、脱敏数据数、总体进度。

异步设计：脱敏在 QThread 跑，主线程 UI 不卡；进度回调经 pyqtSignal 更新界面。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from maskit.stats import MaskStats

# 支持的格式（显示用）
SUPPORTED_HINT = "csv / xlsx / json / eml / msg / pdf / docx / png(需tesseract)"


class MaskWorker(QThread):
    """后台脱敏线程：避免大文件冻结 UI。"""

    progress = pyqtSignal(int, int, int)   # (已处理文件, 总文件, 当前文件进度0-100)
    stats = pyqtSignal(int, int)           # (处理数据数, 脱敏数据数)
    finished_file = pyqtSignal(int, str, str, str)  # (文件索引, 文件名, 状态, 输出路径)
    all_done = pyqtSignal()

    def __init__(self, files: list[str], scan_names: bool, strategy: str, pepper: str | None,
                 ruleset_name: str | None = None, output_dir: str | None = None):
        super().__init__()
        self.files = files
        self.scan_names = scan_names
        self.strategy = strategy
        self.pepper = pepper
        self.ruleset_name = ruleset_name
        self.output_dir = output_dir
        self.total_stats = MaskStats()

    def run(self):
        from maskit.io import default_output_path, mask_file
        from maskit.rules.user_rules import get_current_ruleset, load_ruleset

        # 加载选中的规则集（主界面下拉）；缺省用当前规则集
        name = self.ruleset_name or get_current_ruleset()
        ruleset = load_ruleset(name)
        total = len(self.files)
        for i, f in enumerate(self.files):
            src = Path(f)
            out = default_output_path(f, self.output_dir)
            try:
                details = {}
                mask_file(
                    str(src), str(out), ruleset, self.pepper,
                    strategy=self.strategy, scan_names=self.scan_names,
                    details=details,
                )
                self.total_stats.files += 1
                # 累加处理/脱敏数据（各格式从 details 提供）
                self.total_stats.add(
                    processed=details.get("processed", 0),
                    masked=details.get("masked", 0),
                )
                self.stats.emit(self.total_stats.processed, self.total_stats.masked)
                # Excel 多 sheet：显示各 sheet 处理信息
                info = src.name
                sheets = details.get("sheets")
                if sheets:
                    masked_sheets = [s for s in sheets if s["masked_cells"] > 0]
                    info += f" ({len(sheets)} sheets"
                    if masked_sheets:
                        info += f", {len(masked_sheets)} sheets含脱敏"
                    info += ")"
                self.finished_file.emit(i, info, "成功", str(out))
            except Exception as exc:  # noqa: BLE001 — GUI 层捕获所有异常显示在结果列表
                self.finished_file.emit(i, src.name, f"失败: {exc}", "")
            self.progress.emit(i + 1, total, 100 if i == total - 1 else int((i + 1) / total * 100))
        self.all_done.emit()


class DropArea(QFrame):
    """拖拽文件区域。"""

    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(80)
        self.setStyleSheet("QFrame { border: 2px dashed #aaa; border-radius: 8px; }")
        layout = QVBoxLayout(self)
        hint = QLabel("拖拽文件到这里，或点击「浏览文件」\n" + SUPPORTED_HINT)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        from maskit.io import discover_files

        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        files = []
        for p in paths:
            if os.path.isfile(p):
                files.append(p)
            elif os.path.isdir(p):
                files.extend(discover_files(p))  # 文件夹递归扫描
        self.files_dropped.emit(files)


class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ITA-Maskit 数据脱敏工具")
        self.resize(720, 560)
        self.files: list[str] = []
        self.worker = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # ① 文件选择
        file_row = QHBoxLayout()
        self.file_label = QLabel("未选择文件")
        self.file_label.setStyleSheet("color: #666;")
        browse_btn = QPushButton("浏览文件/文件夹...")
        browse_btn.clicked.connect(self._browse)
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_files)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(browse_btn)
        file_row.addWidget(clear_btn)
        layout.addLayout(file_row)

        # 拖拽区域
        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self._add_files)
        layout.addWidget(self.drop_area)

        # 文件列表（多文件预览 + 勾选 + 状态）
        self.file_table = QTableWidget(0, 3)
        self.file_table.setHorizontalHeaderLabels(["文件名", "状态", "大小"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.file_table.setMinimumHeight(120)
        layout.addWidget(self.file_table, 1)

        # 产出目录
        out_row = QHBoxLayout()
        out_label = QLabel("输出到:")
        self.out_input = QLineEdit()
        self.out_input.setPlaceholderText("留空 = 与原文件同目录")
        out_browse = QPushButton("浏览...")
        out_browse.clicked.connect(self._browse_output_dir)
        out_row.addWidget(out_label)
        out_row.addWidget(self.out_input, 1)
        out_row.addWidget(out_browse)
        layout.addLayout(out_row)

        # ② 选项
        options_row = QHBoxLayout()
        self.scan_names_cb = QCheckBox("遮盖姓名/公司名")
        self.scan_names_cb.setChecked(True)
        self.pseudo_cb = QCheckBox("确定性伪名化")
        self.pepper_input = QLineEdit()
        self.pepper_input.setPlaceholderText("伪名化密钥（勾选伪名化时必填）")
        self.pepper_input.setEchoMode(QLineEdit.Password)
        self.pepper_input.setEnabled(False)
        self.pseudo_cb.toggled.connect(self.pepper_input.setEnabled)
        options_row.addWidget(self.scan_names_cb)
        options_row.addWidget(self.pseudo_cb)
        options_row.addWidget(self.pepper_input, 1)
        layout.addLayout(options_row)

        # 规则集选择
        rs_row = QHBoxLayout()
        rs_label = QLabel("脱敏规则:")
        self.rs_combo = QComboBox()
        self._reload_rulesets()
        rs_row.addWidget(rs_label)
        rs_row.addWidget(self.rs_combo, 1)
        rs_hint = QLabel("（可到规则管理里新建/切换）")
        rs_hint.setStyleSheet("color: #888; font-size: 11px;")
        rs_row.addWidget(rs_hint)
        layout.addLayout(rs_row)

        # 规则管理入口
        rules_row = QHBoxLayout()
        rules_btn = QPushButton("规则管理（可视化编辑）")
        rules_btn.setStyleSheet("color: #2d6cdf; background: #eef3fd; padding: 4px 12px; border-radius: 4px;")
        rules_btn.clicked.connect(self._open_rules_manager)
        rules_row.addWidget(rules_btn)
        rules_row.addStretch()
        layout.addLayout(rules_row)

        # ③ 开始按钮
        self.start_btn = QPushButton("开始脱敏")
        self.start_btn.setStyleSheet(
            "QPushButton { background: #2d6cdf; color: white; padding: 8px; font-size: 15px; "
            "border-radius: 6px; } QPushButton:hover { background: #1e5ac0; }"
        )
        self.start_btn.clicked.connect(self._start)
        layout.addWidget(self.start_btn)

        # ④ 进度区
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_label = QLabel("0/0 文件")
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.progress_label)
        layout.addLayout(progress_row)

        stats_row = QHBoxLayout()
        self.processed_label = QLabel("处理数据: 0")
        self.masked_label = QLabel("脱敏数据: 0")
        self.processed_label.setStyleSheet("font-weight: bold;")
        self.masked_label.setStyleSheet("font-weight: bold;")
        stats_row.addWidget(self.processed_label)
        stats_row.addWidget(self.masked_label)
        stats_row.addStretch()
        layout.addLayout(stats_row)

        # ⑤ 结果列表
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(["文件名", "状态", "输出路径"])
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 列宽：文件名自适应、状态固定、路径拉伸
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.result_table.setColumnWidth(1, 120)
        # 双击打开文件
        self.result_table.cellDoubleClicked.connect(self._open_cell_file)
        layout.addWidget(self.result_table, 1)

        # 打开输出文件夹按钮
        self.open_btn = QPushButton("打开结果文件夹")
        self.open_btn.clicked.connect(self._open_output_dir)
        self.open_btn.setEnabled(False)
        layout.addWidget(self.open_btn)

    # --- 交互 ---

    def _open_rules_manager(self):
        from maskit.gui_rules import RulesManagerDialog

        dlg = RulesManagerDialog(self)
        dlg.exec_()

    def _browse(self):

        files, _ = QFileDialog.getOpenFileNames(
            self, "选择要脱敏的文件",
            "",
            "数据文件 (*.csv *.xlsx *.xls *.json *.jsonl *.ndjson *.eml *.msg *.pdf *.docx *.png *.jpg *.jpeg)",
        )
        if files:
            self._add_files(files)

    def _add_files(self, paths: list[str]):
        """加入文件：校验防传错 → 填充文件列表。"""
        from maskit.io import validate_files

        valid, invalid = validate_files(paths)
        # 防传错提示
        if invalid:
            QMessageBox.warning(
                self, "部分文件无法处理",
                f"已忽略 {len(invalid)} 个文件：\n" + "\n".join(
                    f"  {Path(i['path']).name}: {i['reason']}" for i in invalid[:5]
                ) + ("\n  ..." if len(invalid) > 5 else ""),
            )
        # 去重加入
        for f in valid:
            if f not in self.files:
                self.files.append(f)
        self._refresh_file_table()

    def _refresh_file_table(self):
        """刷新文件列表表格。"""
        import os as _os

        self.file_table.setRowCount(len(self.files))
        for r, f in enumerate(self.files):
            name_item = QTableWidgetItem(Path(f).name)
            name_item.setToolTip(f)
            status_item = QTableWidgetItem("待处理")
            size = _os.path.getsize(f) if _os.path.isfile(f) else 0
            size_item = QTableWidgetItem(f"{size/1024:.0f} KB" if size >= 1024 else f"{size} B")
            self.file_table.setItem(r, 0, name_item)
            self.file_table.setItem(r, 1, status_item)
            self.file_table.setItem(r, 2, size_item)
        self.file_label.setText(f"已选 {len(self.files)} 个文件")

    def _clear_files(self):
        self.files = []
        self.file_table.setRowCount(0)
        self.file_label.setText("未选择文件")

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.out_input.setText(d)

    def _reload_rulesets(self):
        """刷新规则集下拉，默认选中当前规则集。"""
        from maskit.rules.user_rules import get_current_ruleset, list_rulesets

        self.rs_combo.blockSignals(True)
        self.rs_combo.clear()
        self.rs_combo.addItems(list_rulesets())
        current = get_current_ruleset()
        idx = self.rs_combo.findText(current)
        if idx >= 0:
            self.rs_combo.setCurrentIndex(idx)
        self.rs_combo.blockSignals(False)

    def _start(self):
        if not self.files:
            QMessageBox.warning(self, "提示", "请先选择或拖入文件。")
            return
        if self.pseudo_cb.isChecked() and not self.pepper_input.text():
            QMessageBox.warning(self, "提示", "勾选了伪名化，请填写密钥。")
            return

        strategy = "pseudo" if self.pseudo_cb.isChecked() else "mask"
        pepper = self.pepper_input.text() if self.pseudo_cb.isChecked() else None
        ruleset_name = self.rs_combo.currentText() if hasattr(self, "rs_combo") else None
        output_dir = self.out_input.text().strip() or None

        self.start_btn.setEnabled(False)
        self.result_table.setRowCount(0)
        self.processed_label.setText("处理数据: 0")
        self.masked_label.setText("脱敏数据: 0")
        self.progress_bar.setValue(0)
        # 文件列表状态重置为待处理
        for r in range(self.file_table.rowCount()):
            self.file_table.item(r, 1).setText("待处理")

        self.worker = MaskWorker(
            self.files, self.scan_names_cb.isChecked(), strategy, pepper,
            ruleset_name=ruleset_name, output_dir=output_dir,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.stats.connect(self._on_stats)
        self.worker.finished_file.connect(self._on_file_done)
        self.worker.all_done.connect(self._on_all_done)
        self.worker.start()

    # --- 回调 ---

    def _on_progress(self, done: int, total: int, pct: int):
        self.progress_bar.setValue(pct)
        self.progress_label.setText(f"{done}/{total} 文件")

    def _on_stats(self, processed: int, masked: int):
        self.processed_label.setText(f"处理数据: {processed:,}")
        self.masked_label.setText(f"脱敏数据: {masked:,}")

    def _on_file_done(self, idx: int, name: str, status: str, out: str):
        # 更新文件列表状态
        if 0 <= idx < self.file_table.rowCount():
            self.file_table.item(idx, 1).setText(status)
        # 更新结果表
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        name_item = QTableWidgetItem(name)
        status_item = QTableWidgetItem(status)
        out_item = QTableWidgetItem(out)
        # 成功绿色 / 失败红色
        if status.startswith("成功"):
            color = QColor(232, 245, 233)  # 浅绿
        elif status.startswith("失败"):
            color = QColor(253, 237, 237)  # 浅红
        else:
            color = QColor(255, 255, 255)
        for item in (name_item, status_item, out_item):
            item.setBackground(color)
        self.result_table.setItem(row, 0, name_item)
        self.result_table.setItem(row, 1, status_item)
        self.result_table.setItem(row, 2, out_item)

    def _open_cell_file(self, row: int, _col: int):
        """双击打开该行的输出文件/目录。"""
        item = self.result_table.item(row, 2)
        if item and item.text():
            self._open_path(item.text())

    def _open_path(self, path: str):
        p = Path(path)
        if sys.platform == "win32":
            if p.exists():
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                os.startfile(str(p.parent))  # type: ignore[attr-defined]
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(p if p.exists() else p.parent)])

    def _on_all_done(self):
        self.start_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        QMessageBox.information(self, "完成", "所有文件脱敏完成。")

    def _open_output_dir(self):
        # 打开第一个有输出路径的目录
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 2)
            if item and item.text():
                self._open_path(item.text())
                return


def run_gui() -> None:
    """GUI 入口。"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
