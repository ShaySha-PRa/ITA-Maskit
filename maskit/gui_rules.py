"""规则管理 GUI（规则可视化编辑）。

面向不懂代码的审计人员：可视化查看/编辑/添加/删除脱敏规则，
保存到 ~/.maskit/user_rules.yaml，脱敏时自动使用。
"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from maskit.rules.user_rules import (
    delete_user_rules,
    get_rule_defs,
    rules_for_gui,
    save_user_rules,
    user_rules_path,
)


class RuleEditDialog(QDialog):
    """规则编辑对话框（新增/编辑通用）。"""

    def __init__(self, parent=None, rule_name: str = "", rule: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑规则" if rule else "新增规则")
        self.setMinimumWidth(480)
        rule = rule or {}

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_input = QLineEdit(rule_name)
        self.match_input = QLineEdit(rule.get("match", ""))
        self.match_input.setPlaceholderText("Python 正则，如 \\d{17}[\\dX]")
        self.mask_input = QLineEdit(rule.get("mask", ""))
        self.mask_input.setPlaceholderText("遮盖模板，如 {head:6}****{tail:4}")
        self.pseudo_input = QLineEdit(rule.get("pseudo", ""))
        self.pseudo_input.setPlaceholderText("伪名模板，如 BC-{hash:8}")
        form.addRow("规则名:", self.name_input)
        form.addRow("匹配正则:", self.match_input)
        form.addRow("遮盖模板:", self.mask_input)
        form.addRow("伪名模板:", self.pseudo_input)
        layout.addLayout(form)

        hint = QLabel("占位符: {hash:8} 确定性哈希 / {first} 首字 / {head:6} 前6 / {tail:4} 尾4")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox()
        validate_btn = buttons.addButton("校验", QDialogButtonBox.ActionRole)
        ok_btn = buttons.addButton("确定", QDialogButtonBox.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.RejectRole)
        validate_btn.clicked.connect(self._validate)
        ok_btn.clicked.connect(self._accept)
        layout.addWidget(buttons)

    def _validate(self):
        from maskit.rules.user_rules import validate_rule_def

        try:
            validate_rule_def(
                self.name_input.text(),
                {
                    "match": self.match_input.text(),
                    "mask": self.mask_input.text(),
                    "pseudo": self.pseudo_input.text(),
                },
            )
            QMessageBox.information(self, "校验通过", "规则定义合法。")
        except ValueError as exc:
            QMessageBox.warning(self, "校验失败", str(exc))

    def _accept(self):
        from maskit.rules.user_rules import validate_rule_def

        try:
            validate_rule_def(
                self.name_input.text(),
                {
                    "match": self.match_input.text(),
                    "mask": self.mask_input.text(),
                    "pseudo": self.pseudo_input.text(),
                },
            )
        except ValueError as exc:
            QMessageBox.warning(self, "校验失败", str(exc))
            return
        self.accept()

    def get_data(self) -> tuple[str, dict]:
        """返回 (规则名, 规则定义 dict)。"""
        return (
            self.name_input.text().strip(),
            {
                "version": "1.0",
                "match": self.match_input.text(),
                "mask": self.mask_input.text(),
                "pseudo": self.pseudo_input.text(),
            },
        )


class RulesManagerDialog(QDialog):
    """规则管理窗口：列表 + 编辑/新增/删除 + 保存。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("规则管理")
        self.resize(720, 480)
        self.defs = get_rule_defs()
        self.builtin_names = {"name", "email", "ip", "phone", "employee_id",
                              "account", "company", "app_version", "id_card", "bank_card"}

        layout = QVBoxLayout(self)

        # 标题
        title = QLabel(f"规则可视化编辑（保存到 {user_rules_path()}）")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # 规则表格
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["规则名", "来源", "匹配正则", "遮盖模板", "伪名模板"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        # 操作按钮
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 新增规则")
        edit_btn = QPushButton("编辑选中")
        del_btn = QPushButton("删除选中")
        add_btn.clicked.connect(self._add_rule)
        edit_btn.clicked.connect(self._edit_rule)
        del_btn.clicked.connect(self._delete_rule)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 底部：保存 / 恢复默认 / 关闭
        bottom = QHBoxLayout()
        save_btn = QPushButton("保存到用户规则")
        save_btn.setStyleSheet("background: #2d6cdf; color: white; padding: 6px; border-radius: 4px;")
        reset_btn = QPushButton("恢复内置默认")
        close_btn = QPushButton("关闭")
        save_btn.clicked.connect(self._save)
        reset_btn.clicked.connect(self._reset)
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(save_btn)
        bottom.addWidget(reset_btn)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self._refresh_table()

    def _refresh_table(self):
        """刷新规则表格。"""
        rules = rules_for_gui()
        self.table.setRowCount(len(rules))
        for r, rule in enumerate(rules):
            self.table.setItem(r, 0, QTableWidgetItem(rule["name"]))
            self.table.setItem(r, 1, QTableWidgetItem(rule["source"]))
            self.table.setItem(r, 2, QTableWidgetItem(rule["match"][:40]))
            self.table.setItem(r, 3, QTableWidgetItem(rule["mask"][:30]))
            self.table.setItem(r, 4, QTableWidgetItem(rule["pseudo"][:30]))

    def _selected_rule_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一个规则。")
            return None
        return self.table.item(row, 0).text()

    def _add_rule(self):
        dlg = RuleEditDialog(self)
        if dlg.exec_():
            name, raw = dlg.get_data()
            if name in self.defs:
                QMessageBox.warning(self, "提示", f"规则 {name} 已存在，请用编辑或换名字。")
                return
            self.defs[name] = raw
            self._refresh_table()

    def _edit_rule(self):
        name = self._selected_rule_name()
        if not name:
            return
        dlg = RuleEditDialog(self, rule_name=name, rule=self.defs.get(name, {}))
        if dlg.exec_():
            new_name, raw = dlg.get_data()
            # 改名：删旧加新
            if new_name != name:
                self.defs.pop(name, None)
            self.defs[new_name] = raw
            self._refresh_table()

    def _delete_rule(self):
        name = self._selected_rule_name()
        if not name:
            return
        if QMessageBox.question(
            self, "确认", f"删除规则 {name}？（内置规则删除后恢复默认，脱敏不再用它）"
        ) != QMessageBox.Yes:
            return
        self.defs.pop(name, None)
        self._refresh_table()

    def _save(self):
        """保存到用户规则文件。"""
        try:
            save_user_rules(self.defs)
            QMessageBox.information(self, "已保存", f"规则已保存到 {user_rules_path()}\n下次脱敏自动使用。")
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def _reset(self):
        """恢复内置默认（删除用户规则文件）。"""
        if QMessageBox.question(
            self, "确认", "删除所有自定义规则，恢复内置默认？"
        ) != QMessageBox.Yes:
            return
        delete_user_rules()
        self.defs = get_rule_defs()
        self._refresh_table()
        QMessageBox.information(self, "已恢复", "已恢复内置默认规则。")
