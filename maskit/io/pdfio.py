"""PDF 读写。

两条路径并存：
1. **默认（旧）**：pypdf 提取文本 → mask_text_pii → reportlab 重排。
   近似保格式，会丢失字体/表格/图片位置。
2. **beta（--pdf-redact）**：PyMuPDF 在原页上 search → redact 黑块/替换文字，
   保留版式。依赖 pymupdf（AGPL），需显式启用。
"""
from __future__ import annotations

from pathlib import Path

from maskit.rules.defs import RuleSet
from maskit.text import iter_text_pii_hits, mask_text_pii

# reportlab 用于写 PDF；pypdf 用于读（旧路径）
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


def _mask_pdf_rewrite(
    src: Path,
    dst: Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str,
    scan_names: bool,
    person_list: set[str] | None,
) -> int:
    """旧路径：提取 → 脱敏 → reportlab 重排。"""
    pages = _read_pdf_text(src)
    if not pages:
        raise ValueError(f"PDF 文件无文本内容: {src}")

    masked_pages = [
        mask_text_pii(p, ruleset, pepper, strategy, scan_names, person_list) for p in pages
    ]
    _write_pdf_text(dst, masked_pages)
    return len(masked_pages)


def _mask_pdf_redact(
    src: Path,
    dst: Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str,
    scan_names: bool,
    person_list: set[str] | None,
) -> int:
    """beta 路径：PyMuPDF 原页 redaction，保留版式。"""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ValueError(
            "PDF 原样遮罩（beta）需要安装 pymupdf（AGPL）：pip install 'ita-maskit[pdf]' "
            "或 pip install pymupdf"
        ) from exc

    try:
        doc = fitz.open(str(src))
    except Exception as exc:
        raise ValueError(f"无法读取 PDF 文件: {src} ({exc})") from exc

    try:
        for page in doc:
            text = page.get_text() or ""
            hits = iter_text_pii_hits(
                text, ruleset, pepper, strategy, scan_names, person_list
            )
            for original, replacement in hits:
                rects = page.search_for(original)
                for rect in rects:
                    if strategy == "pseudo":
                        # 黑底上填伪名（字号随框高近似）
                        fontsize = max(6, min(11, rect.height * 0.8))
                        page.add_redact_annot(
                            rect,
                            text=replacement,
                            fill=(0, 0, 0),
                            text_color=(1, 1, 1),
                            fontsize=fontsize,
                        )
                    else:
                        # mask：黑块遮罩
                        page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()
        doc.save(str(dst), garbage=4, deflate=True)
        return doc.page_count
    finally:
        doc.close()


def mask_pdf_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
    scan_names: bool = False,
    person_list: set[str] | None = None,
    pdf_redact: bool = False,
) -> int:
    """脱敏 PDF → PDF，返回页数。

    pdf_redact=False（默认）：提取重排旧路径。
    pdf_redact=True（beta）：PyMuPDF 原样遮罩。
    """
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    if pdf_redact:
        return _mask_pdf_redact(src, dst, ruleset, pepper, strategy, scan_names, person_list)
    return _mask_pdf_rewrite(src, dst, ruleset, pepper, strategy, scan_names, person_list)
