"""语言包自动下载测试：ensure_tessdata + _ocr_lang。

数据边界：只下载 tesseract 语言数据（非脱敏数据）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import maskit.io.imageio as imageio


@pytest.fixture
def tessdata_env(tmp_path, monkeypatch):
    """隔离语言包目录 + 清理 TESSDATA_PREFIX。"""
    d = tmp_path / "tessdata"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(imageio, "_TESSDATA_DIR", d)
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    return d


def test_ensure_tessdata_downloads_missing(tessdata_env, monkeypatch):
    """缺失时下载三个语言包并设置 TESSDATA_PREFIX。"""
    import urllib.request

    downloaded = []

    def fake_urlretrieve(url, filename):
        downloaded.append(Path(filename).name)
        Path(filename).write_bytes(b"fake-data")

    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

    d = imageio.ensure_tessdata()
    assert set(downloaded) == {
        "chi_sim.traineddata", "eng.traineddata", "osd.traineddata",
    }
    assert (d / "chi_sim.traineddata").exists()
    assert os.environ["TESSDATA_PREFIX"] == str(d)


def test_ensure_tessdata_skips_existing(tessdata_env, monkeypatch):
    """已存在的语言包不重复下载。"""
    import urllib.request

    (tessdata_env / "chi_sim.traineddata").write_bytes(b"x")
    calls = []
    monkeypatch.setattr(urllib.request, "urlretrieve",
                        lambda url, fn: calls.append(Path(fn).name))
    imageio.ensure_tessdata()
    assert "chi_sim.traineddata" not in calls
    assert set(calls) == {"eng.traineddata", "osd.traineddata"}


def test_ensure_tessdata_download_failure_degrades(tessdata_env, monkeypatch):
    """下载失败不抛异常（降级继续，不阻断脱敏）。"""
    import urllib.request

    def boom(url, filename):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlretrieve", boom)
    d = imageio.ensure_tessdata()  # 不应抛异常
    assert not (d / "chi_sim.traineddata").exists()


def test_ocr_lang_prefers_chinese(tessdata_env):
    """中文包就位 → chi_sim+eng。"""
    (tessdata_env / "chi_sim.traineddata").write_bytes(b"x")
    assert imageio._ocr_lang() == "chi_sim+eng"


def test_ocr_lang_fallback_eng(tessdata_env):
    """无中文包 → 退回 eng。"""
    assert imageio._ocr_lang() == "eng"
