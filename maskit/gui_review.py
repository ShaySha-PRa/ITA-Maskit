"""HITL 复核工作台：只展示 fingerprint / 遮盖预览，不展示原文。"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from maskit.detection.allowlist import Allowlist, default_allowlist_path
from maskit.detection.review import load_review_manifest, row_exposes_raw_value


class ReviewWorkbenchDialog(QDialog):
    """复核清单：加入白名单（按 fingerprint），永不展示原文。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("复核清单")
        self.resize(960, 480)
        self.rows: list[dict] = []
        self.allowlist = Allowlist.load(default_allowlist_path())
        self._path: Path | None = None

        layout = QVBoxLayout(self)
        self.summary = QLabel("未加载复核清单")
        self.summary.setStyleSheet("font-weight: bold; padding: 2px;")
        layout.addWidget(self.summary)

        hint = QLabel(
            "只显示 fingerprint 与遮盖预览。加入白名单后，下次脱敏将跳过该条（按指纹，不存原文）。"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["文件", "列", "类型", "校验", "fingerprint", "预览", "白名单"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        btns = QHBoxLayout()
        load_btn = QPushButton("打开 JSONL…")
        load_btn.clicked.connect(self._browse)
        allow_btn = QPushButton("将选中项加入白名单")
        allow_btn.clicked.connect(self._allow_selected)
        save_btn = QPushButton("保存白名单")
        save_btn.clicked.connect(self._save_allowlist)
        btns.addWidget(load_btn)
        btns.addWidget(allow_btn)
        btns.addWidget(save_btn)
        btns.addStretch()
        layout.addLayout(btns)

        close = QDialogButtonBox()
        close.addButton("关闭", QDialogButtonBox.RejectRole)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def load_path(self, path: str | Path) -> None:
        src = Path(path)
        self._path = src
        self.rows = load_review_manifest(src)
        if any(row_exposes_raw_value(r) for r in self.rows):
            QMessageBox.warning(self, "清单含原文", "该清单含 original_value，界面不会显示原文。")
        self._refresh()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开复核清单", "", "JSONL (*.jsonl);;All (*)"
        )
        if path:
            self.load_path(path)

    def _refresh(self) -> None:
        self.table.setRowCount(len(self.rows))
        allowed_n = 0
        for i, row in enumerate(self.rows):
            et = str(row.get("entity_type") or "")
            fp = str(row.get("fingerprint") or "")
            allowed = self.allowlist.allows(et, "", fingerprint=fp)
            if allowed:
                allowed_n += 1
            cells = [
                Path(str(row.get("file") or "")).name,
                str(row.get("column") or ""),
                et,
                str(row.get("validation_status") or ""),
                fp,
                str(row.get("preview") or ""),
                "是" if allowed else "",
            ]
            color = QColor(232, 245, 233) if allowed else QColor(255, 255, 255)
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(color)
                self.table.setItem(i, c, item)
        self.summary.setText(
            f"共 {len(self.rows)} 条待复核 · 已入白名单 {allowed_n}"
            + (f" · {self._path.name}" if self._path else "")
        )

    def _allow_selected(self) -> None:
        indexes = {idx.row() for idx in self.table.selectedIndexes()}
        if not indexes:
            QMessageBox.information(self, "提示", "请先选中要加入白名单的行。")
            return
        for i in indexes:
            if 0 <= i < len(self.rows):
                row = self.rows[i]
                fp = str(row.get("fingerprint") or "")
                et = str(row.get("entity_type") or "")
                if fp and et:
                    self.allowlist.add_fingerprint(et, fp, reason="gui review")
        self._refresh()

    def _save_allowlist(self) -> None:
        dest = self.allowlist.save()
        QMessageBox.information(self, "已保存", f"白名单已写入\n{dest}")
