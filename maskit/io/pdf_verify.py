"""PDF output verification. FAIL CLOSED. Reports never include raw PII."""

from __future__ import annotations

import hashlib
from pathlib import Path


class RedactionVerificationError(ValueError):
    """Output still contains detected originals."""


def _fp(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                parts.append("")
        return "\n".join(parts)
    except Exception:  # noqa: BLE001
        return ""


def _pypdf_extra_text(path: Path) -> tuple[str, list[str]]:
    """Metadata, form fields, attachments. Returns (blob, checked_layers)."""
    layers = ["text"]
    chunks: list[str] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        meta = reader.metadata
        if meta:
            layers.append("metadata")
            for v in meta.values():
                if v:
                    chunks.append(str(v))
        if getattr(reader, "attachments", None):
            layers.append("embedded_files")
            try:
                for name, data in (reader.attachments or {}).items():
                    chunks.append(str(name))
                    if isinstance(data, (bytes, bytearray)):
                        chunks.append(data.decode("utf-8", errors="ignore"))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, (bytes, bytearray)):
                                chunks.append(item.decode("utf-8", errors="ignore"))
            except Exception:  # noqa: BLE001, S110
                pass
        try:
            if reader.get_fields():
                layers.append("form_fields")
                for field in (reader.get_fields() or {}).values():
                    if isinstance(field, dict):
                        for v in field.values():
                            if v:
                                chunks.append(str(v))
        except Exception:  # noqa: BLE001, S110
            pass
    except Exception:  # noqa: BLE001, S110
        pass
    return "\n".join(chunks), layers


def _pymupdf_extra(path: Path) -> tuple[str, list[str], bool]:
    """Annotations if PyMuPDF is installed. Returns (blob, layers, available)."""
    try:
        import fitz
    except ImportError:
        return "", [], False
    chunks: list[str] = []
    layers = ["annotations"]
    try:
        doc = fitz.open(str(path))
        try:
            for page in doc:
                for annot in page.annots() or []:
                    info = annot.info or {}
                    for key in ("content", "title", "subject"):
                        if info.get(key):
                            chunks.append(str(info[key]))
                for widget in page.widgets() or []:
                    val = getattr(widget, "field_value", None)
                    if val:
                        chunks.append(str(val))
        finally:
            doc.close()
    except Exception:  # noqa: BLE001
        return "", layers, True
    return "\n".join(chunks), layers, True


def verify_pdf_no_originals(
    output_path: str | Path,
    originals: list[str],
    *,
    fail_closed: bool = True,
) -> dict:
    """Reopen output and search for original detected strings.

    Report contains fingerprints only. Layers the current deps cannot cover
    are marked PARTIALLY_VERIFIED, never claimed fully safe.
    """
    dst = Path(output_path)
    text = extract_pdf_text(dst)
    extra, layers = _pypdf_extra_text(dst)
    fitz_blob, fitz_layers, fitz_ok = _pymupdf_extra(dst)
    blob = "\n".join(x for x in (text, extra, fitz_blob) if x)
    leaked = [o for o in originals if o and o in blob]
    checked = layers + fitz_layers
    unverified = []
    if not fitz_ok:
        unverified.extend(["annotations", "ocr_layer", "incremental_update"])
    unverified.append("incremental_update")
    # de-dupe
    seen: set[str] = set()
    unverified = [u for u in unverified if not (u in seen or seen.add(u))]
    partial = bool(unverified)
    if leaked:
        status = "FAIL"
    elif originals and not (text or "").strip():
        status = "PARTIALLY_VERIFIED"
        partial = True
    elif partial:
        status = "PARTIALLY_VERIFIED"
    else:
        status = "PASS"
    report = {
        "status": status,
        "checked": len(originals),
        "leaked": len(leaked),
        "fingerprints": [_fp(o) for o in leaked],
        "partial": partial,
        "layers_checked": checked,
        "layers_unverified": unverified,
    }
    if leaked and fail_closed:
        try:
            dst.unlink()
        except OSError:
            pass
        raise RedactionVerificationError(
            f"PDF 回扫失败：输出中仍可提取 {len(leaked)} 处原文，已隔离输出文件"
        )
    return report
