"""文件流水线后端测试：validate_files / default_output_path。"""

from maskit.io import default_output_path, validate_files

# --- validate_files ---

def test_validate_supported_files(tmp_path):
    """支持的扩展名 → 有效。"""
    f = tmp_path / "a.csv"
    f.write_text("x")
    valid, invalid = validate_files([str(f)])
    assert valid == [str(f)]
    assert invalid == []


def test_validate_unsupported_file(tmp_path):
    """不支持的扩展名 → 无效。"""
    f = tmp_path / "a.txt"
    f.write_text("x")
    valid, invalid = validate_files([str(f)])
    assert valid == []
    assert len(invalid) == 1
    assert "不支持" in invalid[0]["reason"]


def test_validate_missing_path(tmp_path):
    """不存在的文件 → 无效。"""
    valid, invalid = validate_files([str(tmp_path / "nope.xlsx")])
    assert valid == []
    assert invalid[0]["reason"] == "路径不存在"


def test_validate_folder_expands(tmp_path):
    """文件夹 → 展开支持的扩展名。"""
    (tmp_path / "a.csv").write_text("x")
    (tmp_path / "b.xlsx").write_bytes(b"x")
    (tmp_path / "c.txt").write_text("x")
    valid, invalid = validate_files([str(tmp_path)])
    assert len(valid) == 2
    assert invalid == []


def test_validate_mixed(tmp_path):
    """混合：有效文件 + 不支持 + 不存在。"""
    good = tmp_path / "a.csv"
    good.write_text("x")
    bad = tmp_path / "b.txt"
    bad.write_text("x")
    valid, invalid = validate_files([str(good), str(bad), str(tmp_path / "gone.pdf")])
    assert valid == [str(good)]
    assert len(invalid) == 2


# --- default_output_path ---

def test_output_default_same_dir(tmp_path):
    """未指定目录 → 原目录 + _masked 后缀。"""
    f = tmp_path / "data.csv"
    out = default_output_path(str(f))
    assert out == str(tmp_path / "data_masked.csv")


def test_output_custom_dir(tmp_path):
    """指定目录 → 输出到该目录，保留后缀。"""
    f = tmp_path / "data.csv"
    outdir = tmp_path / "out"
    out = default_output_path(str(f), str(outdir))
    assert out == str(outdir / "data_masked.csv")
    assert outdir.exists()  # 目录已创建


def test_output_keeps_extension(tmp_path):
    """输出保留原扩展名。"""
    f = tmp_path / "data.xlsx"
    out = default_output_path(str(f))
    assert out.endswith("_masked.xlsx")
