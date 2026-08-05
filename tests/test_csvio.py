"""数据后端测试：CSV 端到端、边缘情况、确定性、性能断言。"""
import csv
import time

import pytest

from maskit.io.csvio import mask_csv_file
from maskit.rules.loader import load_ruleset

# 简单测试数据（含各类敏感字段 + 一个未映射列 + null）
TEST_CSV = """name,email,ip,phone,employee_id,account,company,app_version,note
张伟,alice@corp.example,10.1.2.3,13800000000,EID-7F3A,zhangsan,亚玛芬体育,v1.2.3,keep
李娜,alice@corp.example,10.1.2.4,138-0000-0001,EID-9B2C,lisi,MayAir,v2.0.0,keep2
,carol@outlook.com,10.1.2.5,,,u3,Acme Inc,v3.1.0,keep3
"""

# 带 pseudo 规则的 YAML
PSEUDO_YAML = """rules:
  - column: phone
    rule: phone
    strategy: pseudo
  - column: email
    rule: email
    strategy: pseudo
  - column: ip
    rule: ip
    strategy: mask
  - column: name
    rule: name
    strategy: mask
"""


@pytest.fixture
def input_csv(tmp_path):
    p = tmp_path / "input.csv"
    p.write_text(TEST_CSV, encoding="utf-8")
    return p


@pytest.fixture
def pseudo_yaml(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text(PSEUDO_YAML, encoding="utf-8")
    return p


def _read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_mask_csv_end_to_end(input_csv, tmp_path):
    """CSV 端到端：全 mask 默认规则集。"""
    out = tmp_path / "out.csv"
    ruleset = load_ruleset()
    rows = mask_csv_file(input_csv, out, ruleset, None)
    assert rows == 3
    data = _read(out)
    # 全部 8 敏感列被处理，note 列透传
    assert data[0]["name"] == "张*"
    assert data[0]["ip"] == "*.*.*.*"
    assert data[0]["note"] == "keep"
    # 未映射列保留
    assert "note" in data[0]


def test_mask_csv_pseudo_requires_pepper(input_csv, pseudo_yaml, tmp_path):
    """pseudo 激活但缺 pepper → 报错。"""
    out = tmp_path / "out.csv"
    ruleset = load_ruleset(pseudo_yaml)
    with pytest.raises(ValueError, match="pepper"):
        mask_csv_file(input_csv, out, ruleset, None)


def test_pseudo_cross_file_determinism(input_csv, pseudo_yaml, tmp_path):
    """双确定性：同输入同 pepper 两次 → 逐字节一致；跨表规范化一致。"""
    ruleset = load_ruleset(pseudo_yaml)
    out1 = tmp_path / "out1.csv"
    out2 = tmp_path / "out2.csv"
    mask_csv_file(input_csv, out1, ruleset, "pepper-X")
    mask_csv_file(input_csv, out2, ruleset, "pepper-X")
    assert out1.read_bytes() == out2.read_bytes()  # 逐字节一致

    data = _read(out1)
    # 跨表规范化：13800000000 与 138-0000-0001 → 各自确定性映射
    # 注意它们不同源值，应映射到不同伪名
    assert data[0]["phone"] != data[1]["phone"]
    assert len(data[0]["phone"]) == 11  # 保留位数


def test_missing_column_errors(input_csv, tmp_path):
    """规则引用不存在列 → 硬错误列出列名。"""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("rules:\n  - column: no_such_col\n    rule: name\n    strategy: mask\n", encoding="utf-8")
    ruleset = load_ruleset(bad_yaml)
    out = tmp_path / "out.csv"
    with pytest.raises(ValueError, match="no_such_col"):
        mask_csv_file(input_csv, out, ruleset, None)


def test_null_passthrough(input_csv, tmp_path):
    """null 保持 null（空字符串透传）。"""
    out = tmp_path / "out.csv"
    ruleset = load_ruleset()
    mask_csv_file(input_csv, out, ruleset, None)
    data = _read(out)
    assert data[2]["name"] == ""  # 空姓名保持空
    assert data[2]["employee_id"] == ""  # 空员工号保持空


def test_unmapped_columns_passthrough(input_csv, tmp_path):
    """未映射列原样透传。"""
    out = tmp_path / "out.csv"
    ruleset = load_ruleset()
    mask_csv_file(input_csv, out, ruleset, None)
    data = _read(out)
    assert data[0]["note"] == "keep"


def test_row_order_preserved(input_csv, tmp_path):
    """行序与输入一致。"""
    out = tmp_path / "out.csv"
    ruleset = load_ruleset()
    mask_csv_file(input_csv, out, ruleset, None)
    data = _read(out)
    assert data[0]["company"] == "亚*"
    assert data[1]["company"] == "M*"
    assert data[2]["company"] == "A*"


def test_empty_file_errors(tmp_path):
    """空文件 → 报无数据错误。"""
    empty = tmp_path / "empty.csv"
    empty.write_text("name,email\n", encoding="utf-8")
    ruleset = load_ruleset()
    out = tmp_path / "out.csv"
    with pytest.raises(ValueError, match="无数据"):
        mask_csv_file(empty, out, ruleset, None)


# --- 性能断言（CI 用 1 万行 < 1 秒） ---

def test_performance_10k_rows_under_1s(tmp_path):
    """性能断言：1 万行脱敏 < 1 秒（CI 参考机）。"""
    from maskit.demo import generate_demo_data

    src = tmp_path / "perf_input.csv"
    out = tmp_path / "perf_out.csv"
    generate_demo_data(rows=10_000).write_csv(src)

    ruleset = load_ruleset()
    start = time.perf_counter()
    mask_csv_file(src, out, ruleset, None)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"1 万行耗时 {elapsed:.2f}s，超过 1 秒阈值"
