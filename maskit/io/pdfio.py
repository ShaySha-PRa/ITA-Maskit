"""PDF 读写。

有 PyMuPDF 时按页分流：
- 数字原生：span 几何原页黑块（不再把 search_for 当主路径）
- 扫描页：pixmap + 本地 Tesseract 词框映射后黑块；缺 OCR 则失败

无 PyMuPDF：数字原生回退 pypdf + reportlab 重排；扫描页不得走重排冒充成功。
"""
from __future__ import annotations

from pathlib import Path

from maskit.detection.pipeline import detect_text
from maskit.detection.policy import current_checksum_policy, partition_hits
from maskit.io.ocr_boxes import (
    SCAN_OCR_REQUIRED,
    image_to_data,
    ocr_available,
    ocr_sensitive_boxes,
)
from maskit.io.pdf_classify import KIND_SCAN, page_kind
from maskit.rules.defs import RuleSet
from maskit.text import mask_text_pii

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

_PIXMAP_SCALE = 2.0


def _fitz():
    try:
        import fitz
    except ImportError:
        return None
    return fitz


def _read_pdf_text(src: Path) -> list[str]:
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
        except Exception:  # noqa: BLE001
            pages.append("")
    return pages


def _write_pdf_text(dst: Path, pages: list[str]) -> None:
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
    pages = _read_pdf_text(src)
    if not pages:
        raise ValueError(f"PDF 文件无文本内容: {src}")
    if any(page_kind(p) == KIND_SCAN for p in pages):
        raise ValueError(SCAN_OCR_REQUIRED)
    masked_pages = [
        mask_text_pii(p, ruleset, pepper, strategy, scan_names, person_list) for p in pages
    ]
    _write_pdf_text(dst, masked_pages)
    return len(masked_pages)


def _page_spans(page) -> tuple[str, list[tuple[int, int, tuple[float, float, float, float]]]]:
    """Concatenate span text and record (start, end, bbox)."""
    info = page.get_text("dict") or {}
    pieces: list[str] = []
    spans: list[tuple[int, int, tuple[float, float, float, float]]] = []
    pos = 0
    for block in info.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = span.get("text") or ""
                if not t:
                    continue
                start = pos
                pieces.append(t)
                pos += len(t)
                bbox = span.get("bbox") or (0, 0, 0, 0)
                spans.append((start, pos, (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))))
            pieces.append("\n")
            pos += 1
    return "".join(pieces), spans


def _redact_digital_page(page, ruleset: RuleSet, scan_names: bool, person_list: set[str] | None) -> list[str]:
    fitz = _fitz()
    text, spans = _page_spans(page)
    if not text.strip():
        return []
    hits = detect_text(
        text, ruleset=ruleset, person_list=person_list, scan_names=scan_names
    )
    auto = partition_hits(hits, checksum_policy=current_checksum_policy())["AUTO_APPLY"]
    originals: list[str] = []
    for h in auto:
        originals.append(h.original_value)
        a, b = h.span(len(text))
        for ts, te, bbox in spans:
            if ts < b and a < te:
                page.add_redact_annot(fitz.Rect(*bbox), fill=(0, 0, 0))
    page.apply_redactions()
    return originals


def _page_to_pil(page, fitz):
    from PIL import Image

    pix = page.get_pixmap(matrix=fitz.Matrix(_PIXMAP_SCALE, _PIXMAP_SCALE), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples), pix.width, pix.height


def _redact_scan_page(
    page,
    ruleset: RuleSet,
    scan_names: bool,
    person_list: set[str] | None,
    *,
    allow_ocr: bool,
) -> list[str]:
    if not allow_ocr or not ocr_available():
        raise ValueError(SCAN_OCR_REQUIRED)
    fitz = _fitz()
    img, pw, ph = _page_to_pil(page, fitz)
    try:
        data = image_to_data(img)
    except Exception as exc:
        raise ValueError(SCAN_OCR_REQUIRED) from exc
    boxes, originals = ocr_sensitive_boxes(
        data, ruleset, person_list=person_list, scan_names=scan_names
    )
    sx = page.rect.width / max(pw, 1)
    sy = page.rect.height / max(ph, 1)
    for x0, y0, x1, y1 in boxes:
        page.add_redact_annot(
            fitz.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy),
            fill=(0, 0, 0),
        )
    page.apply_redactions()
    return originals


def _mask_pdf_hybrid(
    src: Path,
    dst: Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str,
    scan_names: bool,
    person_list: set[str] | None,
    allow_ocr: bool,
) -> tuple[int, list[str], list[int]]:
    """Return (page_count, originals, scan_page_indices). Scan pages always black-box."""
    del pepper, strategy  # scan pages never paint pseudo; digital uses detect+black box
    fitz = _fitz()
    try:
        doc = fitz.open(str(src))
    except Exception as exc:
        raise ValueError(f"无法读取 PDF 文件: {src} ({exc})") from exc
    originals: list[str] = []
    scan_pages: list[int] = []
    try:
        for i, page in enumerate(doc):
            kind = page_kind(page.get_text() or "")
            if kind == KIND_SCAN:
                scan_pages.append(i)
                originals.extend(
                    _redact_scan_page(
                        page, ruleset, scan_names, person_list, allow_ocr=allow_ocr
                    )
                )
            else:
                originals.extend(
                    _redact_digital_page(page, ruleset, scan_names, person_list)
                )
        doc.save(str(dst), garbage=4, deflate=True)
        return doc.page_count, originals, scan_pages
    except Exception:
        if dst.exists():
            try:
                dst.unlink()
            except OSError:
                pass
        raise
    finally:
        doc.close()


def _verify_after_write(
    src: Path,
    dst: Path,
    ruleset: RuleSet,
    person_list: set[str] | None,
    scan_names: bool,
    originals: list[str],
    scan_pages: list[int],
) -> None:
    from maskit.detection.runctx import current_run
    from maskit.io.pdf_verify import verify_pdf_no_originals, verify_scan_ocr_no_originals

    if not originals:
        for page in _read_pdf_text(src):
            for h in detect_text(
                page, ruleset=ruleset, person_list=person_list, scan_names=scan_names
            ):
                originals.append(h.original_value)
    current_run().pdf_verify = verify_pdf_no_originals(
        dst, originals, fail_closed=True
    )
    if scan_pages:
        verify_scan_ocr_no_originals(dst, originals, scan_pages, fail_closed=True)


def mask_pdf_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
    scan_names: bool = False,
    person_list: set[str] | None = None,
    pdf_redact: bool = True,
    verify: bool = True,
    pdf_ocr: bool = True,
) -> int:
    """脱敏 PDF → PDF，返回页数。

    pdf_redact=True（默认）：有 PyMuPDF 则按页原样遮罩，否则数字原生回退重排。
    pdf_redact=False：强制提取重排（扫描页仍失败）。
    """
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    originals: list[str] = []
    scan_pages: list[int] = []
    use_hybrid = bool(pdf_redact) and _fitz() is not None
    if use_hybrid:
        n, originals, scan_pages = _mask_pdf_hybrid(
            src, dst, ruleset, pepper, strategy, scan_names, person_list, pdf_ocr
        )
    else:
        n = _mask_pdf_rewrite(src, dst, ruleset, pepper, strategy, scan_names, person_list)
    if verify:
        _verify_after_write(
            src, dst, ruleset, person_list, scan_names, originals, scan_pages
        )
    return n
