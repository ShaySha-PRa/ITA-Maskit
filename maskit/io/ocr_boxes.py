"""Shared Tesseract word-box mapping for image crop and PDF scan pages.

Does not send business images anywhere. Language packs are tesseract data only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from maskit.detection.pipeline import detect_text
from maskit.detection.policy import partition_hits
from maskit.detection.scope import ChecksumPolicy
from maskit.rules.defs import RuleSet

OCR_AUTO_MIN = 0.85

_TESSDATA_DIR = Path.home() / ".maskit" / "tessdata"
_TESSDATA_BASE = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/"
_TESSDATA_LANGS = ("chi_sim", "eng", "osd")

SCAN_OCR_REQUIRED = (
    "扫描页需要本机 Tesseract OCR。请安装 tesseract 后重试"
    "（pip install 'ita-maskit[image]' 并安装 tesseract 二进制）。"
    "仅含可选中文字的 PDF 不需要 OCR。"
)


def ensure_tessdata(progress=None) -> Path:
    """Ensure chi_sim/eng/osd exist under ~/.maskit/tessdata/."""
    import urllib.request

    _TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["TESSDATA_PREFIX"] = str(_TESSDATA_DIR)
    if progress is None:
        progress = lambda m: print(m, file=sys.stderr)
    for lang in _TESSDATA_LANGS:
        dest = _TESSDATA_DIR / f"{lang}.traineddata"
        if dest.exists():
            continue
        progress(f"首次图片脱敏：自动下载语言包 {lang}.traineddata …")
        try:
            urllib.request.urlretrieve(f"{_TESSDATA_BASE}{lang}.traineddata", dest)
        except Exception as exc:  # noqa: BLE001
            progress(
                f"警告：语言包 {lang}.traineddata 下载失败（{exc}）。\n"
                "如识别中文不准确，请手动把 tessdata 放回 tesseract 的 tessdata 目录。"
            )
    return _TESSDATA_DIR


def ocr_lang() -> str:
    if (_TESSDATA_DIR / "chi_sim.traineddata").exists():
        return "chi_sim+eng"
    return "eng"


def load_tesseract():
    try:
        import pytesseract
    except ImportError as exc:
        raise ValueError(
            "需要安装 pytesseract 和 tesseract OCR。"
            "安装：pip install pytesseract，并安装 tesseract 二进制。"
        ) from exc
    ensure_tessdata()
    return pytesseract


def ocr_available() -> bool:
    try:
        pytesseract = load_tesseract()
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def image_to_data(img) -> dict:
    pytesseract = load_tesseract()
    return pytesseract.image_to_data(
        img, lang=ocr_lang(), output_type=pytesseract.Output.DICT
    )


def ocr_plain_text(img) -> str:
    data = image_to_data(img)
    words = [(t or "").strip() for t in data.get("text", [])]
    return " ".join(w for w in words if w)


def ocr_sensitive_boxes(
    data: dict,
    ruleset: RuleSet,
    *,
    person_list: set[str] | None = None,
    scan_names: bool = False,
) -> tuple[list[tuple[int, int, int, int]], list[str]]:
    """Map detect_text hits back to OCR boxes. Returns (boxes, auto original values)."""
    n = len(data["text"])
    pieces: list[str] = []
    token_spans: list[tuple[int, int, int]] = []
    pos = 0
    for i in range(n):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        if pieces:
            pieces.append(" ")
            pos += 1
        start = pos
        pieces.append(word)
        pos += len(word)
        token_spans.append((start, pos, i))
    blob = "".join(pieces)
    if not blob.strip():
        return [], []
    hits = detect_text(
        blob, ruleset=ruleset, person_list=person_list, scan_names=scan_names
    )
    auto = partition_hits(hits, checksum_policy=ChecksumPolicy.REVIEW.value)["AUTO_APPLY"]
    boxes: list[tuple[int, int, int, int]] = []
    originals: list[str] = []
    for h in auto:
        if h.confidence < OCR_AUTO_MIN:
            continue
        if h.validation_status == "INVALID":
            continue
        originals.append(h.original_value)
        a, b = h.span(len(blob))
        for ts, te, idx in token_spans:
            if ts < b and a < te:
                x, y, w, hgt = (
                    data["left"][idx],
                    data["top"][idx],
                    data["width"][idx],
                    data["height"][idx],
                )
                if w > 0 and hgt > 0:
                    boxes.append((x, y, x + w, y + hgt))
    return boxes, originals
