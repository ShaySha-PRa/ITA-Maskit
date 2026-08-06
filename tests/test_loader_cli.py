"""YAML 规则加载 + CLI 测试。"""
import subprocess
import sys

import pytest

from maskit.rules.loader import list_rules, load_ruleset

# 数据驱动规则：覆盖内置 + 新增自定义
CUSTOM_YAML = """rule_defs:
  ip:
    version: "1.1"
    match: '^\\d{1,3}(\\.\\d{1,3}){3}$'
    mask: '*.*.*.*'
    pseudo: 'IP-{hash:8}'
  tin:
    version: "1.0"
    match: '^[A-Z0-9]{15,18}$'
    mask: '***-{tail:4}'
    pseudo: 'TIN-{hash:8}'
rules:
  - column: ip
    rule: ip
    strategy: mask
  - column: tin
    rule: tin
    strategy: pseudo
"""


def test_default_ruleset_all_mask():
    """无 --rules → 内置默认规则集，全部 mask。"""
    rs = load_ruleset()
    assert len(rs.specs) == 8  # name/email/ip/phone/employee_id/account/company/app_version
    assert all(s.strategy == "mask" for s in rs.specs)


def test_custom_rule_defs_override_and_add(tmp_path):
    """数据驱动：YAML 覆盖内置 ip + 新增自定义 tin。"""
    p = tmp_path / "custom.yaml"
    p.write_text(CUSTOM_YAML, encoding="utf-8")
    rs = load_ruleset(p)
    # 覆盖后 ip 定义更新
    assert rs.defs["ip"].version == "1.1"
    assert rs.defs["ip"].mask == "*.*.*.*"
    # 新增 tin
    assert "tin" in rs.defs
    assert rs.defs["tin"].pseudo == "TIN-{hash:8}"
    # 列映射
    assert rs.strategy_for("ip") == "mask"
    assert rs.strategy_for("tin") == "pseudo"


def test_missing_rules_file(tmp_path):
    """规则文件不存在 → FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        load_ruleset(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path):
    """YAML 非法 → ValueError。"""
    p = tmp_path / "bad.yaml"
    p.write_text("rules: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_ruleset(p)


def test_missing_rule_fields(tmp_path):
    """规则定义缺必填字段 → 报错。"""
    p = tmp_path / "incomplete.yaml"
    p.write_text("rule_defs:\n  foo:\n    match: 'x'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mask"):
        load_ruleset(p)


def test_bad_strategy(tmp_path):
    """非法策略 → 报错。"""
    p = tmp_path / "badstrat.yaml"
    p.write_text("rules:\n  - column: name\n    rule: name\n    strategy: encrypt\n", encoding="utf-8")
    with pytest.raises(ValueError, match="encrypt"):
        load_ruleset(p)


def test_ruleset_version_tracks_defs():
    """规则集版本随定义变化（审计可追溯）。"""
    rs1 = load_ruleset()
    rs2 = load_ruleset()
    assert rs1.version == rs2.version  # 同定义同版本


def test_rules_list_has_12():
    """rules list 显示 12 条（10 默认 + 2 默认关闭）。"""
    rules = list_rules()
    assert len(rules) == 12
    disabled = [r for r in rules if r["default_disabled"]]
    assert len(disabled) == 2  # ssn, credit_card


# --- CLI 测试（子进程） ---

def _run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "maskit.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(_repo_root()),
        check=False,
    )


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]


def test_cli_missing_pepper_exit_2(tmp_path):
    """pseudo 无 pepper → 退出码 2，无 traceback。"""
    src = tmp_path / "in.csv"
    src.write_text("phone\n13800000000\n", encoding="utf-8")
    rules = tmp_path / "r.yaml"
    rules.write_text("rules:\n  - column: phone\n    rule: phone\n    strategy: pseudo\n", encoding="utf-8")
    r = _run_cli("mask", str(src), "--rules", str(rules))
    assert r.returncode == 2
    assert "pepper" in r.stderr
    assert "Traceback" not in r.stderr


def test_cli_missing_input_exit_2(tmp_path):
    """输入文件不存在 → 退出码 2。"""
    r = _run_cli("mask", str(tmp_path / "nope.csv"))
    assert r.returncode == 2
    assert "不存在" in r.stderr


def test_cli_success_exit_0(tmp_path):
    """成功 → 退出码 0，审计日志写入。"""
    src = tmp_path / "in.csv"
    src.write_text("name,email\n张伟,a@b.com\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    r = _run_cli("mask", str(src), "-o", str(out))
    assert r.returncode == 0
    assert out.exists()
    assert "已脱敏" in r.stdout


def test_cli_version():
    r = _run_cli("--version")
    assert r.returncode == 0
    assert "ITA-maskit" in r.stdout


def test_cli_demo(tmp_path):
    """demo 生成确定性数据（固定 seed 两次一致）。"""
    d1 = tmp_path / "d1.csv"
    d2 = tmp_path / "d2.csv"
    r = _run_cli("demo", "--rows", "10", "-o", str(d1))
    assert r.returncode == 0
    r2 = _run_cli("demo", "--rows", "10", "-o", str(d2))
    assert r2.returncode == 0
    assert d1.exists()
    assert d1.read_bytes() == d2.read_bytes()  # 固定 seed → 确定性
