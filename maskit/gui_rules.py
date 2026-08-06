"""规则管理 GUI（规则可视化编辑）。

面向不懂代码的审计人员：可视化查看/编辑/添加/删除脱敏规则，
保存到 ~/.maskit/user_rules.yaml，脱敏时自动使用。
"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from maskit.rules.user_rules import (
    get_rule_defs,
    rules_for_gui,
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
        self.desc_input = QLineEdit(rule.get("description", ""))
        self.desc_input.setPlaceholderText("用通俗语言描述这个规则，如「18位身份证号」")
        self.match_input = QLineEdit(rule.get("match", ""))
        self.match_input.setPlaceholderText("Python 正则，如 \\d{17}[\\dX]")
        self.mask_input = QLineEdit(rule.get("mask", ""))
        self.mask_input.setPlaceholderText("遮盖模板，如 {head:6}****{tail:4}")
        self.pseudo_input = QLineEdit(rule.get("pseudo", ""))
        self.pseudo_input.setPlaceholderText("伪名模板，如 BC-{hash:8}")
        form.addRow("规则名:", self.name_input)
        form.addRow("描述:", self.desc_input)
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
                "description": self.desc_input.text().strip(),
                "match": self.match_input.text(),
                "mask": self.mask_input.text(),
                "pseudo": self.pseudo_input.text(),
            },
        )


class RulesManagerDialog(QDialog):
    """规则管理窗口：规则集切换 + 列表 + 编辑/新增/删除 + 导入导出。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("规则管理")
        self.resize(760, 520)
        self._reload_defs()
        self.builtin_names = {"name", "email", "ip", "phone", "employee_id",
                              "account", "company", "app_version", "id_card", "bank_card"}

        layout = QVBoxLayout(self)

        # 规则集区
        rs_row = QHBoxLayout()
        rs_label = QLabel("当前规则集:")
        self.rs_combo = QComboBox()
        self._reload_rs_combo()
        self.rs_combo.currentTextChanged.connect(self._on_rs_changed)
        new_btn = QPushButton("新建")
        saveas_btn = QPushButton("另存为")
        import_btn = QPushButton("导入")
        export_btn = QPushButton("导出")
        del_btn = QPushButton("删除")
        builtin_btn = QPushButton("内置默认")
        new_btn.clicked.connect(self._new_ruleset)
        saveas_btn.clicked.connect(self._save_as)
        import_btn.clicked.connect(self._import_ruleset)
        export_btn.clicked.connect(self._export_ruleset)
        del_btn.clicked.connect(self._delete_ruleset)
        builtin_btn.clicked.connect(lambda: self._switch_to("内置默认"))
        rs_row.addWidget(rs_label)
        rs_row.addWidget(self.rs_combo, 1)
        rs_row.addWidget(new_btn)
        rs_row.addWidget(saveas_btn)
        rs_row.addWidget(import_btn)
        rs_row.addWidget(export_btn)
        rs_row.addWidget(del_btn)
        rs_row.addWidget(builtin_btn)
        layout.addLayout(rs_row)

        title = QLabel(f"规则集目录: {user_rules_path()}")
        title.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(title)

        # 规则表格
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["规则名", "来源", "描述", "遮盖方式", "伪名方式"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        # AI 生成规则区
        ai_row = QHBoxLayout()
        ai_label = QLabel("🤖 AI 生成规则:")
        self.ai_input = QLineEdit()
        self.ai_input.setPlaceholderText("用一句话描述规则要求，如「新增车牌号脱敏，保留省份和尾两位」")
        ai_btn = QPushButton("生成")
        ai_btn.setStyleSheet("background: #28a745; color: white; padding: 4px 12px; border-radius: 4px;")
        ai_btn.clicked.connect(self._ai_generate_rule)
        ai_row.addWidget(ai_label)
        ai_row.addWidget(self.ai_input, 1)
        ai_row.addWidget(ai_btn)
        layout.addLayout(ai_row)

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

        # 底部：保存当前规则集 / 关闭
        bottom = QHBoxLayout()
        save_btn = QPushButton("保存当前规则集")
        save_btn.setStyleSheet("background: #2d6cdf; color: white; padding: 6px; border-radius: 4px;")
        close_btn = QPushButton("关闭")
        save_btn.clicked.connect(self._save)
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(save_btn)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        self._refresh_table()

    # --- 规则集 ---

    def _reload_defs(self):
        """加载当前规则集的完整定义。"""

        self.defs = get_rule_defs()

    def _reload_rs_combo(self):
        """刷新规则集下拉，保持当前选中。"""
        from maskit.rules.user_rules import get_current_ruleset, list_rulesets

        self.rs_combo.blockSignals(True)
        self.rs_combo.clear()
        self.rs_combo.addItems(list_rulesets())
        current = get_current_ruleset()
        idx = self.rs_combo.findText(current)
        if idx >= 0:
            self.rs_combo.setCurrentIndex(idx)
        self.rs_combo.blockSignals(False)

    def _on_rs_changed(self, name: str):
        """切换规则集 → 重载定义 + 刷新列表。"""
        from maskit.rules.user_rules import set_current_ruleset

        if name:
            try:
                set_current_ruleset(name)
            except ValueError:
                pass
            self._reload_defs()
            self._refresh_table()

    def _switch_to(self, name: str):
        from maskit.rules.user_rules import set_current_ruleset

        try:
            set_current_ruleset(name)
        except ValueError as exc:
            QMessageBox.warning(self, "提示", str(exc))
            return
        self._reload_rs_combo()
        self._reload_defs()
        self._refresh_table()

    def _new_ruleset(self):
        """新建空规则集。"""
        from maskit.rules.user_rules import BUILTIN_RS, save_ruleset

        name, ok = QInputDialog.getText(self, "新建规则集", "规则集名称:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if name == BUILTIN_RS or name in [n for n in self._all_names() if n != BUILTIN_RS]:
            QMessageBox.warning(self, "提示", "该规则集已存在。")
            return
        save_ruleset(name, {n: dict(r) for n, r in self.defs.items()})
        self._switch_to(name)

    def _all_names(self):
        from maskit.rules.user_rules import list_rulesets

        return list_rulesets()

    def _save_as(self):
        """当前规则集另存为新的规则集。"""
        from maskit.rules.user_rules import save_ruleset

        name, ok = QInputDialog.getText(self, "另存为", "新规则集名称:")
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            save_ruleset(name, self.defs)
            self._switch_to(name)
        except ValueError as exc:
            QMessageBox.warning(self, "提示", str(exc))

    def _import_ruleset(self):
        """从文件导入规则集。"""
        from maskit.rules.user_rules import import_ruleset

        path, _ = QFileDialog.getOpenFileName(self, "选择规则文件", "", "规则文件 (*.yaml *.yml)")
        if not path:
            return
        try:
            import_ruleset(path)
            self._reload_rs_combo()
            self._reload_defs()
            self._refresh_table()
            QMessageBox.information(self, "已导入", "已导入并设为当前规则集。")
        except ValueError as exc:
            QMessageBox.warning(self, "导入失败", str(exc))

    def _export_ruleset(self):
        """导出当前规则集到文件。"""
        from maskit.rules.user_rules import BUILTIN_RS, export_ruleset

        if self._current_rs_name() == BUILTIN_RS:
            QMessageBox.information(self, "提示", "内置默认规则集无需导出。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出规则集", "ruleset.yaml", "规则文件 (*.yaml)")
        if not path:
            return
        export_ruleset(self._current_rs_name(), path)
        QMessageBox.information(self, "已导出", f"已导出到 {path}")

    def _delete_ruleset(self):
        """删除当前规则集（不能删内置/当前生效的）。"""
        from maskit.rules.user_rules import BUILTIN_RS, delete_ruleset

        name = self._current_rs_name()
        if name == BUILTIN_RS:
            QMessageBox.information(self, "提示", "不能删除「内置默认」规则集。")
            return
        if QMessageBox.question(self, "确认", f"删除规则集 {name}？") != QMessageBox.Yes:
            return
        try:
            delete_ruleset(name)
        except ValueError as exc:
            QMessageBox.warning(self, "提示", str(exc))
            return
        self._switch_to(BUILTIN_RS)

    def _current_rs_name(self) -> str:
        return self.rs_combo.currentText()

    def _refresh_table(self):
        """刷新规则表格。

        列表显示通俗描述（方便非开发人员看懂），
        真实正则/模板放在 tooltip（悬停可见，便于微调）。
        """
        rules = rules_for_gui()
        self.table.setRowCount(len(rules))
        for r, rule in enumerate(rules):
            name_item = QTableWidgetItem(rule["name"])
            name_item.setToolTip(f"规则名: {rule['name']}")
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, QTableWidgetItem(rule["source"]))
            # 描述为主，真实正则作 tooltip
            desc = rule["description"] or rule["match"][:40]
            desc_item = QTableWidgetItem(desc[:50])
            desc_item.setToolTip(f"匹配正则: {rule['match']}\n\n{desc}")
            self.table.setItem(r, 2, desc_item)
            # 遮盖/伪名模板：显示描述，模板作 tooltip
            mask_desc = rule["mask"]
            mask_item = QTableWidgetItem(mask_desc[:40])
            mask_item.setToolTip(f"遮盖模板: {mask_desc}")
            self.table.setItem(r, 3, mask_item)
            pseudo_desc = rule["pseudo"]
            pseudo_item = QTableWidgetItem(pseudo_desc[:40])
            pseudo_item.setToolTip(f"伪名模板: {pseudo_desc}")
            self.table.setItem(r, 4, pseudo_item)

    def _selected_rule_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选择一个规则。")
            return None
        return self.table.item(row, 0).text()

    def _ai_generate_rule(self):
        """AI 生成规则：输入要求 → 调 LLM → 校验 → 存入当前规则集。

        数据边界：只有用户输入的描述发给 LLM，脱敏数据永不出本地。
        """

        from maskit.llm import LLMClient, LLMConfig
        from maskit.rules.user_rules import BUILTIN_RS

        request = self.ai_input.text().strip()
        if not request:
            QMessageBox.information(self, "提示", "请先输入规则要求，如「新增车牌号脱敏，保留省份和尾两位」。")
            return

        # 当前规则集是内置默认 → 不能直接存，提示先新建/切换
        if self._current_rs_name() == BUILTIN_RS:
            QMessageBox.information(
                self, "提示",
                "当前是「内置默认」规则集（只读）。\nAI 生成的规则需要一个可保存的规则集，\n请先「新建」或「另存为」一套规则集。",
            )
            return

        try:
            config = LLMConfig.from_env()
        except ValueError as exc:
            QMessageBox.warning(
                self, "未配置 API",
                f"{exc}\n\n请在环境变量设置 MASKIT_LLM_API_KEY 后重启程序。",
            )
            return

        # 调用 LLM（异步避免卡 UI）
        from PyQt5.QtCore import QThread, pyqtSignal

        class _GenWorker(QThread):
            done = pyqtSignal(str, str)  # (yaml, error)
            def __init__(self, request, config):
                super().__init__()
                self.request = request
                self.config = config

            def run(self):
                try:
                    client = LLMClient(self.config)
                    yaml_text = client.generate_rules(self.request)
                    self.done.emit(yaml_text, "")
                except Exception as exc:  # noqa: BLE001 — GUI 层捕获所有异常
                    self.done.emit("", str(exc))

        self._gen_worker = _GenWorker(request, config)
        self._gen_worker.done.connect(
            lambda yaml_text, err: self._on_ai_done(yaml_text, err)
        )
        QMessageBox.information(self, "AI 生成中", "正在调用 AI 生成规则，请稍候...")
        self._gen_worker.start()

    def _on_ai_done(self, yaml_text: str, err: str):
        """AI 生成完成后：校验 → 展示 → 确认存入。"""
        import re

        from maskit.rules.loader import load_ruleset_from_string

        if err:
            QMessageBox.warning(self, "AI 调用失败", err)
            return

        # 去掉 markdown 代码块包裹
        clean = re.sub(r"^```yaml\s*|\s*```$", "", yaml_text).strip()
        try:
            rs = load_ruleset_from_string(clean)
        except ValueError as exc:
            QMessageBox.warning(self, "规则校验失败", f"AI 生成的规则无法解析：{exc}")
            return

        # 预览生成的新规则
        new_rules = [n for n in rs.defs if n not in self.defs]
        preview = "AI 生成的规则：\n\n" + clean
        preview += f"\n\n（将新增 {len(new_rules)} 条规则到当前规则集）"

        if QMessageBox.question(self, "AI 生成结果", preview + "\n\n确定存入当前规则集？") != QMessageBox.Yes:
            return

        # 存入当前规则集（RuleDef → dict，用 dataclasses.asdict 保留全部字段）
        from dataclasses import asdict

        from maskit.rules.user_rules import BUILTIN_RS, save_ruleset

        current = self._current_rs_name()
        if current == BUILTIN_RS:
            QMessageBox.information(self, "提示", "内置默认规则集不可修改，请先「新建」一套规则集。")
            return
        for name, rule in rs.defs.items():
            self.defs[name] = {k: v for k, v in asdict(rule).items() if v}
        # 保存到当前规则集文件，列表（读文件）即可看到
        try:
            save_ruleset(current, self.defs)
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._refresh_table()
        QMessageBox.information(self, "已添加", f"AI 已生成 {len(new_rules)} 条规则，已保存到规则集「{current}」。")

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
        """保存当前规则集。"""
        from maskit.rules.user_rules import BUILTIN_RS, save_ruleset

        name = self._current_rs_name()
        if name == BUILTIN_RS:
            QMessageBox.information(self, "提示", "内置默认规则集不可修改，请「另存为」新建一套。")
            return
        try:
            save_ruleset(name, self.defs)
            QMessageBox.information(self, "已保存", f"规则集「{name}」已保存。\n下次脱敏自动使用。")
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
