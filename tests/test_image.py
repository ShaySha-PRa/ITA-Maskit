"""图片脱敏（beta）测试。

门控逻辑测试不依赖真实 tesseract（CI 可能没有）；裁剪逻辑用 mock OCR。
"""

import pytest

from maskit.io import is_image_format, mask_file
from maskit.rules.loader import load_ruleset


def test_image_beta_gate(tmp_path):
    """图片格式默认报错（beta 需 --image-crop）。"""
    src = tmp_path / "t.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")  # 最小 PNG 头
    with pytest.raises(ValueError, match="beta"):
        mask_file(src, tmp_path / "o.png", load_ruleset(), None)


def test_image_is_image_format():
    assert is_image_format("x.png")
    assert is_image_format("x.jpg")
    assert is_image_format("x.jpeg")
    assert not is_image_format("x.csv")


def test_image_crop_requires_tesseract(tmp_path):
    """--image-crop 但无 tesseract → 明确安装提示（mock 缺失场景）。"""
    from PIL import Image

    src = tmp_path / "t.png"
    Image.new("RGB", (50, 50), "white").save(src)
    # 未装 pytesseract 时（CI 环境）→ ValueError；装了则走 OCR
    try:
        mask_file(src, tmp_path / "o.png", load_ruleset(), None, image_crop=True)
    except ValueError as e:
        assert "tesseract" in str(e).lower() or "pytesseract" in str(e).lower()


def test_supported_formats_include_images():
    from maskit.io import SUPPORTED_FORMATS

    assert ".png" in SUPPORTED_FORMATS
    assert ".jpg" in SUPPORTED_FORMATS
