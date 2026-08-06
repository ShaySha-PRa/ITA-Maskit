"""敏感信息规定文档 → AI 生成规则：extract_doc_text + 文档生成流程测试。

覆盖：
- extract_doc_text 文本/Word/缺失文件
- 文档文本作为 user_request → mock LLM → 规则可解析
- GUI 上传规定文档 → 提取文本 → 作为 AI 生成输入（含长文档截断）

GUI 测试在子进程运行：PyQt5 与 polars/pyarrow 都自带 ICU 库，
同进程加载会符号冲突导致后续测试段错误，子进程隔离可彻底规避。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from maskit.llm import build_rules_prompt, extract_doc_text
from maskit.rules.loader import load_ruleset_from_string

# mock LLM 返回的合法规则 YAML
VALID_YAML = """rule_defs:
  id_card:
    version: "1.0"
    match: '^\\d{17}[\\dX]$'
    mask: '{head:6}****{tail:4}'
    pseudo: 'ID-{hash:8}'
rules:
  - column: id_card
    rule: id_card
    strategy: mask
"""

DOC_TEXT = "2026年敏感信息规定：\n1. 身份证号必须遮盖\n2. 手机号伪名化\n"

_ROOT = Path(__file__).resolve().parent.parent


# --- extract_doc_text（后端公共函数） ---

def test_extract_doc_text_txt(tmp_path):
    """纯文本文档提取。"""
    f = tmp_path / "2026敏感信息规则.txt"
    f.write_text(DOC_TEXT, encoding="utf-8")
    assert extract_doc_text(str(f)) == DOC_TEXT


def test_extract_doc_text_docx(tmp_path):
    """Word 文档提取（需 python-docx）。"""
    pytest.importorskip("docx")
    from docx import Document

    f = tmp_path / "规定.docx"
    doc = Document()
    doc.add_paragraph("手机号须伪名化")
    doc.save(str(f))
    assert "手机号" in extract_doc_text(str(f))


def test_extract_doc_text_missing_file(tmp_path):
    """文件不存在 → ValueError（GUI/CLI 可捕获提示）。"""
    with pytest.raises(ValueError):
        extract_doc_text(str(tmp_path / "不存在.pdf"))


# --- 文档文本 → LLM → 规则（后端流程，mock LLM） ---

def test_doc_text_flows_into_prompt():
    """文档文本作为 user_request → prompt 包含文档内容。"""
    prompt = build_rules_prompt(DOC_TEXT)
    assert "身份证号" in prompt
    assert "手机号" in prompt


def test_doc_text_generates_parseable_rules():
    """mock LLM：文档文本 → 生成规则 → 可解析为规则集。"""
    from maskit.llm import LLMClient

    class _FakeLLMClient(LLMClient):
        """mock：记录入参，返回预设 YAML。"""

        def __init__(self):
            self.requests: list[str] = []

        def generate_rules(self, user_request: str) -> str:
            self.requests.append(user_request)
            return VALID_YAML

    client = _FakeLLMClient()
    yaml_text = client.generate_rules(DOC_TEXT)
    assert DOC_TEXT in client.requests  # 文档文本确实发给 LLM（数据边界内：只有文档）
    rs = load_ruleset_from_string(yaml_text)
    assert "id_card" in rs.defs
    assert rs.strategy_for("id_card") == "mask"


# --- GUI：上传规定文档 → 提取 → AI 生成（子进程隔离） ---

_GUI_HELPER = r"""
import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['MASKIT_RULESETS_DIR'] = sys.argv[1]
os.environ['MASKIT_CURRENT_RS'] = sys.argv[2]
doc = sys.argv[3]

from PyQt5.QtWidgets import QApplication
app = QApplication([])

# 屏蔽阻塞式弹窗，避免测试挂起
import maskit.gui_rules as gr
for _m in ('information', 'warning'):
    setattr(gr.QMessageBox, _m, staticmethod(lambda *a, **k: None))

from maskit.gui_rules import RulesManagerDialog
dlg = RulesManagerDialog()
dlg.doc_input.setText(doc)
captured = {}
dlg._run_ai_worker = lambda request, source_label='': captured.update(
    request=request, source_label=source_label
)
dlg._ai_generate_from_doc()
req = captured.get('request', '')
print('REQ_LEN', len(req))
print('HAS_ID_CARD', '身份证号' in req)
print('HAS_PHONE', '手机号' in req)
print('LABEL', captured.get('source_label', ''))
print('TRUNC', '截取' in req)
sys.stdout.flush()
os._exit(0)  # 绕过 Qt 退出时清理，避免退出段错误
"""


def _gui_flow(tmp_path: Path, doc_path: str) -> str:
    """在子进程里跑 GUI 流程，返回 stdout。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [
            sys.executable, "-c", _GUI_HELPER,
            str(tmp_path / "rulesets"), str(tmp_path / "current"), str(doc_path),
        ],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert proc.returncode == 0, f"GUI 子进程失败:\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout


def test_gui_generate_from_doc_extracts_text(tmp_path):
    """上传规定文档 → 提取文本 → 作为 AI 生成输入（source_label 为文件名）。"""
    f = tmp_path / "2026敏感信息规则.txt"
    f.write_text(DOC_TEXT, encoding="utf-8")

    out = _gui_flow(tmp_path, str(f))
    assert "HAS_ID_CARD True" in out
    assert "HAS_PHONE True" in out
    assert "2026敏感信息规则.txt" in out


def test_gui_generate_from_doc_missing_file(tmp_path):
    """未选择文档 → 不触发 AI 流程。"""
    out = _gui_flow(tmp_path, "")
    assert "REQ_LEN 0" in out


def test_gui_generate_from_doc_truncates_long(tmp_path):
    """长文档截断到 50,000 字符，避免 prompt 过大。"""
    f = tmp_path / "long.txt"
    f.write_text("第" * 60_000, encoding="utf-8")

    out = _gui_flow(tmp_path, str(f))
    assert "TRUNC True" in out
