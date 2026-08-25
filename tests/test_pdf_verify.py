"""PDF verification reports fingerprints only and admits partial coverage."""

from pathlib import Path

import pytest

from maskit.io.pdf_verify import (
    RedactionVerificationError,
    verify_pdf_no_originals,
    verify_scan_ocr_no_originals,
)


def test_pdf_verify_fail_closed_deletes_output(tmp_path: Path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    dst = tmp_path / "leaky.pdf"
    c = canvas.Canvas(str(dst), pagesize=A4)
    c.drawString(50, 800, "alice@corp.example")
    c.save()
    leaked = "alice@corp.example"
    with pytest.raises(RedactionVerificationError, match="回扫失败") as excinfo:
        verify_pdf_no_originals(dst, [leaked], fail_closed=True)
    assert leaked not in str(excinfo.value)
    assert not dst.exists()


def test_pdf_verify_report_has_unverified_layers(tmp_path: Path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    dst = tmp_path / "clean.pdf"
    c = canvas.Canvas(str(dst), pagesize=A4)
    c.drawString(50, 800, "no pii here")
    c.save()
    report = verify_pdf_no_originals(dst, ["alice@corp.example"], fail_closed=False)
    assert report["status"] in {"PASS", "PARTIALLY_VERIFIED"}
    assert "incremental_update" in report["layers_unverified"]
    assert report["leaked"] == 0


def test_scan_ocr_verify_fail_closed_no_plaintext(tmp_path: Path, monkeypatch):
    pytest.importorskip("fitz")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    dst = tmp_path / "scan_out.pdf"
    c = canvas.Canvas(str(dst), pagesize=A4)
    c.drawString(50, 800, "no text leak")
    c.save()
    leaked = "alice@corp.example"
    monkeypatch.setattr("maskit.io.ocr_boxes.ocr_available", lambda: True)
    monkeypatch.setattr("maskit.io.ocr_boxes.ocr_plain_text", lambda img: leaked)
    with pytest.raises(RedactionVerificationError, match="OCR 回扫失败") as excinfo:
        verify_scan_ocr_no_originals(dst, [leaked], [0], fail_closed=True)
    assert leaked not in str(excinfo.value)
    assert not dst.exists()
