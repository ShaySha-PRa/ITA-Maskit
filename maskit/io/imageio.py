"""图片脱敏（beta）：OCR 定位敏感文字区域 → 裁剪掉（图片变小）。

**beta 功能，默认关闭**：需 `--image-crop` 显式启用。数据全程本地。
PDF 扫描页的 OCR 词框复用 maskit.io.ocr_boxes，本模块仍只做 png/jpg 水平裁带。
"""
from __future__ import annotations

from pathlib import Path

from maskit.io.ocr_boxes import (
    ensure_tessdata,
    image_to_data,
    load_tesseract,
    ocr_lang,
    ocr_sensitive_boxes,
)
from maskit.rules.defs import RuleSet

# tessdata tests import these names from imageio
_ocr_lang = ocr_lang
_load_tesseract = load_tesseract


def _ocr_sensitive_boxes(data: dict, ruleset: RuleSet):
    boxes, _orig = ocr_sensitive_boxes(data, ruleset)
    return boxes


def mask_image_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
) -> int:
    """脱敏图片（裁剪敏感区域）→ 图片，返回处理区域数。"""
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    load_tesseract()

    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("图片脱敏需要 Pillow。安装：pip install pillow") from exc

    try:
        img = Image.open(src).convert("RGB")
    except Exception as exc:
        raise ValueError(f"无法读取图片: {src} ({exc})") from exc

    try:
        data = image_to_data(img)
    except Exception as exc:
        raise ValueError(
            f"OCR 失败（确认已安装 tesseract 及中文语言包）: {src} ({exc})"
        ) from exc

    boxes, _orig = ocr_sensitive_boxes(data, ruleset)

    if not boxes:
        img.save(dst)
        return 0

    min_x = min(b[0] for b in boxes)
    min_y = min(b[1] for b in boxes)
    max_x = max(b[2] for b in boxes)
    max_y = max(b[3] for b in boxes)

    pad = 5
    min_x = max(0, min_x - pad)
    min_y = max(0, min_y - pad)
    max_x = min(img.width, max_x + pad)
    max_y = min(img.height, max_y + pad)

    top_region = img.crop((0, 0, img.width, min_y))
    bottom_region = img.crop((0, max_y, img.width, img.height))

    new_h = top_region.height + bottom_region.height
    result = Image.new("RGB", (img.width, new_h), (255, 255, 255))
    result.paste(top_region, (0, 0))
    result.paste(bottom_region, (0, top_region.height))

    result.save(dst)
    return len(boxes)
