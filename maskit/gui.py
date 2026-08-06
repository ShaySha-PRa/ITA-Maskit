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
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
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
    finished_file = pyqtSignal(str, str, str)  # (文件名, 状态, 输出路径)
    all_done = pyqtSignal()

    def __init__(self, files: list[str], scan_names: bool, strategy: str, pepper: str | None):
        super().__init__()
        self.files = files
        self.scan_names = scan_names
        self.strategy = strategy
        self.pepper = pepper
        self.total_stats = MaskStats()

    def run(self):
        from maskit.io import mask_file
        from maskit.rules.user_rules import load_user_rules

        # 加载用户规则（含 GUI 编辑的自定义规则）；无则内置默认
        ruleset = load_user_rules()
        total = len(self.files)
        for i, f in enumerate(self.files):
            src = Path(f)
            out = src.with_name(src.stem + "_masked" + src.suffix)
            try:
                details = {}
                mask_file(
                    str(src), str(out), ruleset, self.pepper,
                    strategy=self.strategy, scan_names=self.scan_names,
                    details=details,
                )
                self.total_stats.files += 1
                # Excel 多 sheet：显示各 sheet 处理信息
                info = src.name
                sheets = details.get("sheets")
                if sheets:
                    masked_sheets = [s for s in sheets if s["masked_cells"] > 0]
                    info += f" ({len(sheets)} sheets"
                    if masked_sheets:
                        info += f", {len(masked_sheets)} sheets含脱敏"
                    info += ")"
                self.finished_file.emit(info, "成功", str(out))
            except Exception as exc:  # noqa: BLE001 — GUI 层捕获所有异常显示在结果列表
                self.finished_file.emit(src.name, f"失败: {exc}", "")
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
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        self.files_dropped.emit([f for f in files if os.path.isfile(f)])


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
        browse_btn = QPushButton("浏览文件...")
        browse_btn.clicked.connect(self._browse)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # 拖拽区域
        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self._set_files)
        layout.addWidget(self.drop_area)

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
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
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
            self._set_files(files)

    def _set_files(self, files: list[str]):
        self.files = files
        self.file_label.setText(f"已选 {len(files)} 个文件: {Path(files[0]).name}" + (" 等" if len(files) > 1 else ""))

    def _start(self):
        if not self.files:
            QMessageBox.warning(self, "提示", "请先选择或拖入文件。")
            return
        if self.pseudo_cb.isChecked() and not self.pepper_input.text():
            QMessageBox.warning(self, "提示", "勾选了伪名化，请填写密钥。")
            return

        strategy = "pseudo" if self.pseudo_cb.isChecked() else "mask"
        pepper = self.pepper_input.text() if self.pseudo_cb.isChecked() else None

        self.start_btn.setEnabled(False)
        self.result_table.setRowCount(0)
        self.processed_label.setText("处理数据: 0")
        self.masked_label.setText("脱敏数据: 0")
        self.progress_bar.setValue(0)

        self.worker = MaskWorker(
            self.files, self.scan_names_cb.isChecked(), strategy, pepper
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

    def _on_file_done(self, name: str, status: str, out: str):
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        self.result_table.setItem(row, 0, QTableWidgetItem(name))
        self.result_table.setItem(row, 1, QTableWidgetItem(status))
        self.result_table.setItem(row, 2, QTableWidgetItem(out))

    def _on_all_done(self):
        self.start_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        QMessageBox.information(self, "完成", "所有文件脱敏完成。")

    def _open_output_dir(self):
        # 打开最后一个成功输出所在的目录
        for row in range(self.result_table.rowCount()):
            item = self.result_table.item(row, 2)
            if item and item.text():
                d = str(Path(item.text()).parent)
                if sys.platform == "win32":
                    os.startfile(d)  # type: ignore[attr-defined]
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", d])
                return


def run_gui() -> None:
    """GUI 入口。"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
