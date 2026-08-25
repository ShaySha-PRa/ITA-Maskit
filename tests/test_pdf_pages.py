"""PDF per-page classify, digital span redact, scan OCR black boxes."""
from __future__ import annotations

import pytest

from maskit.io import mask_file
from maskit.io.ocr_boxes import SCAN_OCR_REQUIRED, ocr_sensitive_boxes
from maskit.io.pdf_classify import KIND_DIGITAL, KIND_SCAN, MIN_DIGITAL_CHARS, page_kind
from maskit.rules.loader import load_ruleset

EMAIL = "alice@corp.example"


def _text_pdf(path: Path, text: str = f"Contact {EMAIL} office") -> Path:
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    c.setFont("Helvetica", 14)
    c.drawString(72, 720, text)
    c.save()
    return path


def _image_only_pdf(path: Path, text: str = f"Contact {EMAIL} office") -> Path:
    from PIL import Image, ImageDraw
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    img = Image.new("RGB", (800, 240), "white")
    ImageDraw.Draw(img).text((24, 100), text, fill="black")
    c = canvas.Canvas(str(path), pagesize=(400, 120))
    c.drawImage(ImageReader(img), 0, 0, 400, 120)
    c.save()
    return path


def _rasterized_scan_pdf(path: Path, text: str = f"Contact {EMAIL} office") -> Path:
    """Render selectable text, then embed the pixmap so the page has no text layer."""
    fitz = pytest.importorskip("fitz")
    digital = path.parent / f"{path.stem}_digital.pdf"
    _text_pdf(digital, text)
    src = fitz.open(str(digital))
    pix = src[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    src.close()
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    doc.save(str(path))
    doc.close()
    return path


def _hide_fitz(monkeypatch):
    import builtins
    import sys

    monkeypatch.delitem(sys.modules, "fitz", raising=False)
    monkeypatch.delitem(sys.modules, "pymupdf", raising=False)
    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "fitz" or name.startswith("fitz."):
            raise ImportError("no fitz")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)


def test_page_kind_threshold():
    assert MIN_DIGITAL_CHARS == 8
    assert page_kind("") == KIND_SCAN
    assert page_kind("   \n\t  ") == KIND_SCAN
    assert page_kind("1234567") == KIND_SCAN
    assert page_kind("12345678") == KIND_DIGITAL
    assert page_kind("Contact us today") == KIND_DIGITAL


def test_pdf_ocr_disabled_scan_fails(tmp_path):
    src = _image_only_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "out.pdf"
    with pytest.raises(ValueError, match="Tesseract"):
        mask_file(src, out, load_ruleset(), None, pdf_ocr=False)
    assert not out.exists()


def test_scan_without_ocr_fails_and_leaves_no_output(tmp_path, monkeypatch):
    monkeypatch.setattr("maskit.io.pdfio.ocr_available", lambda: False)
    src = _image_only_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "out.pdf"
    with pytest.raises(ValueError, match="Tesseract") as ei:
        mask_file(src, out, load_ruleset(), None, pdf_ocr=True)
    assert EMAIL not in str(ei.value)
    assert SCAN_OCR_REQUIRED in str(ei.value) or "tesseract" in str(ei.value).lower()
    assert not out.exists()


def test_digital_pdf_succeeds_without_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr("maskit.io.pdfio.ocr_available", lambda: False)
    src = _text_pdf(tmp_path / "digital.pdf")
    out = tmp_path / "out.pdf"
    pages = mask_file(src, out, load_ruleset(), None, pdf_ocr=False)
    assert pages == 1
    assert out.exists()
    from pypdf import PdfReader

    assert EMAIL not in (PdfReader(str(out)).pages[0].extract_text() or "")


def test_digital_page_keeps_size_email_gone(tmp_path):
    fitz = pytest.importorskip("fitz")
    src = _text_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    src_doc = fitz.open(str(src))
    src_rect = src_doc[0].rect
    src_doc.close()
    pages = mask_file(src, out, load_ruleset(), None, strategy="mask", pdf_redact=True)
    assert pages == 1
    out_doc = fitz.open(str(out))
    try:
        assert out_doc[0].rect == src_rect
        assert EMAIL not in (out_doc[0].get_text() or "")
    finally:
        out_doc.close()


def test_no_pymupdf_scan_still_fails(tmp_path, monkeypatch):
    _hide_fitz(monkeypatch)
    src = _image_only_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "out.pdf"
    from maskit.io import pdfio

    with pytest.raises(ValueError, match="Tesseract"):
        pdfio.mask_pdf_file(src, out, load_ruleset(), None, pdf_redact=True)
    assert not out.exists()


def test_ocr_sensitive_boxes_reusable_not_crop():
    data = {
        "text": ["Contact", EMAIL, "office"],
        "left": [10, 80, 220],
        "top": [4, 4, 4],
        "width": [60, 120, 50],
        "height": [12, 12, 12],
    }
    boxes, originals = ocr_sensitive_boxes(data, load_ruleset())
    assert EMAIL in originals
    assert (80, 4, 200, 16) in boxes


def test_scan_email_black_box_ocr_gone(tmp_path):
    fitz = pytest.importorskip("fitz")
    from maskit.io.ocr_boxes import ocr_available, ocr_plain_text
    from PIL import Image

    if not ocr_available():
        pytest.skip("tesseract not installed")
    src = _rasterized_scan_pdf(tmp_path / "scan.pdf")
    src_doc = fitz.open(str(src))
    pix = src_doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    src_rect = src_doc[0].rect
    src_doc.close()
    before = ocr_plain_text(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    if EMAIL not in before:
        pytest.skip("tesseract did not read synthetic email")
    out = tmp_path / "out.pdf"
    mask_file(src, out, load_ruleset(), "x", strategy="pseudo", pdf_redact=True)
    out_doc = fitz.open(str(out))
    try:
        assert out_doc[0].rect == src_rect
        assert EMAIL not in (out_doc[0].get_text() or "")
        opix = out_doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        after = ocr_plain_text(Image.frombytes("RGB", (opix.width, opix.height), opix.samples))
    finally:
        out_doc.close()
    assert EMAIL not in after


def test_mixed_pages_scan_fails_without_ocr(tmp_path, monkeypatch):
    fitz = pytest.importorskip("fitz")
    monkeypatch.setattr("maskit.io.pdfio.ocr_available", lambda: False)
    scan = _rasterized_scan_pdf(tmp_path / "s.pdf")
    digital = _text_pdf(tmp_path / "d.pdf", "Invoice 2024 office desk")
    src = tmp_path / "mixed.pdf"
    out_doc = fitz.open()
    out_doc.insert_pdf(fitz.open(str(scan)))
    out_doc.insert_pdf(fitz.open(str(digital)))
    out_doc.save(str(src))
    out_doc.close()
    out = tmp_path / "out.pdf"
    with pytest.raises(ValueError, match="Tesseract"):
        mask_file(src, out, load_ruleset(), None)
    assert not out.exists()


def test_mixed_pages_route_scan_and_digital(tmp_path):
    fitz = pytest.importorskip("fitz")
    from maskit.io.ocr_boxes import ocr_available, ocr_plain_text
    from PIL import Image

    if not ocr_available():
        pytest.skip("tesseract not installed")
    scan = _rasterized_scan_pdf(tmp_path / "s.pdf")
    digital = tmp_path / "d.pdf"
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(digital))
    c.setFont("Helvetica", 14)
    c.drawString(72, 720, f"Contact {EMAIL}")
    c.drawString(72, 690, "Office invoice desk")
    c.save()
    src = tmp_path / "mixed.pdf"
    merged = fitz.open()
    merged.insert_pdf(fitz.open(str(scan)))
    merged.insert_pdf(fitz.open(str(digital)))
    merged.save(str(src))
    merged.close()
    src_doc = fitz.open(str(src))
    pix = src_doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    before = ocr_plain_text(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    src_doc.close()
    if EMAIL not in before:
        pytest.skip("tesseract did not read synthetic email")
    out = tmp_path / "out.pdf"
    mask_file(src, out, load_ruleset(), None, pdf_redact=True)
    out_doc = fitz.open(str(out))
    try:
        opix = out_doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        scan_text = ocr_plain_text(Image.frombytes("RGB", (opix.width, opix.height), opix.samples))
        digital_text = out_doc[1].get_text() or ""
    finally:
        out_doc.close()
    assert EMAIL not in scan_text
    assert EMAIL not in digital_text
    assert "invoice" in digital_text.lower() or "Office" in digital_text or "desk" in digital_text
