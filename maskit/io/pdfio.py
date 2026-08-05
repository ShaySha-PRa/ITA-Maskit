"""PDF 读写。

pypdf 逐页提取文本 → mask_text_pii 全文扫描 → reportlab 重排文本页。
⚠️ 近似保格式：提取再重排会丢失原始排版（字体/表格/图片位置）。
真正的原样遮盖需要 PDF 图层级操作，v2 用近似方案，README 已明示。
"""
from __future__ import annotations

from pathlib import Path

from maskit.rules.defs import RuleSet
from maskit.text import mask_text_pii

# reportlab 用于写 PDF；pypdf 用于读
try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
except ImportError:  # pragma: no cover
    A4 = canvas = mm = None


def _read_pdf_text(src: Path) -> list[str]:
    """提取 PDF 每页文本。"""
    if PdfReader is None:
        raise ValueError("需要安装 pypdf 才能处理 PDF")
    try:
        reader = PdfReader(str(src))
    except Exception as exc:
        raise ValueError(f"无法读取 PDF 文件: {src} ({exc})") from exc
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — 单页提取失败给空页，不中断整份 PDF
            pages.append("")
    return pages


def _write_pdf_text(dst: Path, pages: list[str]) -> None:
    """用 reportlab 重排文本页（近似保格式）。"""
    if canvas is None:
        raise ValueError("需要安装 reportlab 才能写 PDF")
    c = canvas.Canvas(str(dst), pagesize=A4)
    _, height = A4
    margin = 20 * mm
    line_h = 5 * mm
    for page in pages:
        c.setFont("Helvetica", 10)
        y = height - margin
        for line in page.splitlines():
            if y < margin:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - margin
            # 截断超长行（近似排版）
            c.drawString(margin, y, line[:120])
            y -= line_h
        c.showPage()
    c.save()


def mask_pdf_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
    scan_names: bool = False,
    person_list: set[str] | None = None,
) -> int:
    """脱敏 PDF → PDF，返回页数。"""
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    pages = _read_pdf_text(src)
    if not pages:
        raise ValueError(f"PDF 文件无文本内容: {src}")

    masked_pages = [mask_text_pii(p, ruleset, pepper, strategy, scan_names, person_list) for p in pages]
    _write_pdf_text(dst, masked_pages)
    return len(masked_pages)
