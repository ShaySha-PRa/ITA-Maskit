"""图片脱敏（beta）：OCR 定位敏感文字区域 → 裁剪掉（图片变小）。

**beta 功能，默认关闭**：需 `--image-crop` 显式启用。数据全程本地。

流程：
1. tesseract OCR（`image_to_data`）识别图片文字 + 边界框
2. 用现有规则正则判断哪些文字是敏感 PII（email/ip/phone/employee_id…）
3. 收集敏感区域边界框，合并成裁剪区域
4. Pillow 裁剪掉该区域（图片变小），敏感信息彻底移除

依赖：tesseract 二进制（需手动装）+ pytesseract + Pillow。
中文/英文语言包：首次使用时自动下载（tessdata_fast，无需手动找）。
未启用 --image-crop 时，图片格式直接报错（beta，不默认处理）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from maskit.rules.defs import RuleSet
from maskit.text import _strip_anchors

# 语言包：首次图片脱敏时自动下载（tessdata_fast 官方仓库，~28MB 三件套）
_TESSDATA_DIR = Path.home() / ".maskit" / "tessdata"
_TESSDATA_BASE = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/"
# 中文（简体）+ 英文 + 方向检测（OSD，自动分页时可能需要）
_TESSDATA_LANGS = ("chi_sim", "eng", "osd")


def ensure_tessdata(progress=None) -> Path:
    """确保中文/英文语言包就位：缺失则自动下载到 ~/.maskit/tessdata/。

    返回 tessdata 目录，并设置 TESSDATA_PREFIX 让 tesseract 使用它。
    数据边界：只下载 tesseract 语言数据（非脱敏数据）。
    """
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
        except Exception as exc:  # noqa: BLE001 — 下载失败降级，不阻断脱敏
            progress(
                f"警告：语言包 {lang}.traineddata 下载失败（{exc}）。\n"
                "如识别中文不准确，请手动把 tessdata 放回 tesseract 的 tessdata 目录。"
            )
    return _TESSDATA_DIR


def _ocr_lang() -> str:
    """OCR 语言：中文包就位 → chi_sim+eng；否则退回 eng。"""
    if (_TESSDATA_DIR / "chi_sim.traineddata").exists():
        return "chi_sim+eng"
    return "eng"


def _load_tesseract():
    """延迟加载 pytesseract + 校验 tesseract 可用 + 确保语言包。"""
    try:
        import pytesseract
    except ImportError as exc:
        raise ValueError(
            "图片脱敏需要安装 pytesseract 和 tesseract OCR（beta 功能）。"
            "安装：pip install pytesseract，并安装 tesseract 二进制（含中文语言包）。"
        ) from exc
    # 首次使用自动下载中文/英文语言包（beta 图片脱敏）
    ensure_tessdata()
    return pytesseract


def _sensitive_regexes(ruleset: RuleSet) -> list:
    """返回可用于图片文字识别的敏感正则（text_scanable 规则，去锚点）。"""
    import re

    compiled = []
    for d in ruleset.defs.values():
        if d.text_scanable and not d.default_disabled:
            compiled.append(re.compile(_strip_anchors(d.match)))
    return compiled


def _is_sensitive(text: str, regexes: list) -> bool:
    """判断 OCR 文本是否命中敏感正则。"""
    t = (text or "").strip()
    if not t:
        return False
    return any(r.search(t) for r in regexes)


def mask_image_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
) -> int:
    """脱敏图片（裁剪敏感区域）→ 图片，返回处理区域数。

    beta：需 --image-crop 启用（在 mask_file 分发层判断）。
    """
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    pytesseract = _load_tesseract()

    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("图片脱敏需要 Pillow。安装：pip install pillow") from exc

    try:
        img = Image.open(src).convert("RGB")
    except Exception as exc:
        raise ValueError(f"无法读取图片: {src} ({exc})") from exc

    # OCR：逐字/词级别拿文本 + 边界框（中文包就位 → chi_sim+eng 识别中文）
    try:
        data = pytesseract.image_to_data(
            img, lang=_ocr_lang(), output_type=pytesseract.Output.DICT
        )
    except Exception as exc:
        raise ValueError(
            f"OCR 失败（确认已安装 tesseract 及中文语言包）: {src} ({exc})"
        ) from exc

    regexes = _sensitive_regexes(ruleset)
    # 合并敏感词的边界框（同行的合并，避免零碎区域）
    boxes = []
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        conf = int(data.get("conf", [0])[i] if i < len(data.get("conf", [])) else 0)
        if not text or conf < 60:  # 低置信度跳过
            continue
        if _is_sensitive(text, regexes):
            x, y, w, h = (
                data["left"][i], data["top"][i],
                data["width"][i], data["height"][i],
            )
            if w > 0 and h > 0:
                boxes.append((x, y, x + w, y + h))

    if not boxes:
        # 无敏感信息 → 原样复制
        img.save(dst)
        return 0

    # 合并所有敏感框为一个最小外接区域（简单可靠，保证全部移除）
    min_x = min(b[0] for b in boxes)
    min_y = min(b[1] for b in boxes)
    max_x = max(b[2] for b in boxes)
    max_y = max(b[3] for b in boxes)

    # 四周留 5px 边距
    pad = 5
    min_x = max(0, min_x - pad)
    min_y = max(0, min_y - pad)
    max_x = min(img.width, max_x + pad)
    max_y = min(img.height, max_y + pad)

    # 裁剪：保留「上方 + 下方」两块（去掉中间敏感带）
    top_region = img.crop((0, 0, img.width, min_y))
    bottom_region = img.crop((0, max_y, img.width, img.height))

    # 垂直拼接
    new_h = top_region.height + bottom_region.height
    result = Image.new("RGB", (img.width, new_h), (255, 255, 255))
    result.paste(top_region, (0, 0))
    result.paste(bottom_region, (0, top_region.height))

    result.save(dst)
    return len(boxes)
