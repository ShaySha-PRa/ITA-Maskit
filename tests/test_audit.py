"""审计日志测试：JSONL 写入 + domain separation 指纹 + 读取。"""

from maskit.audit import (
    audit_log_path,
    log_run,
    pepper_fingerprint,
    read_logs,
)
from maskit.rules.engine import audit_key, pseudo_key


def test_pepper_fingerprint_deterministic():
    """pepper 指纹确定性且不存明文。"""
    a = pepper_fingerprint("secret")
    b = pepper_fingerprint("secret")
    assert a == b
    assert "secret" not in a  # 不存明文


def test_domain_separation_audit_vs_pseudo():
    """审计指纹与伪名化用不同 key（防交叉泄露）。"""
    assert audit_key("p") != pseudo_key("p")


def test_log_run_and_read(tmp_path, monkeypatch):
    """log_run 写入 JSONL，read_logs 读取。"""
    log_path = tmp_path / "audit.log"
    monkeypatch.setenv("MASKIT_AUDIT_LOG", str(log_path))

    log_run(
        input_file="in.csv",
        output_file="out.csv",
        ruleset_version="sha256:abc",
        pepper="secret-pepper",
        rows=100,
        mask_columns=["name"],
        pseudo_columns=["phone"],
    )

    entries = read_logs()
    assert len(entries) == 1
    e = entries[0]
    assert e["input_file"] == "in.csv"
    assert e["rows"] == 100
    assert e["ruleset_version"] == "sha256:abc"
    assert e["pepper_fingerprint"].startswith("fp:")
    assert e["mask_columns"] == ["name"]
    assert e["pseudo_columns"] == ["phone"]


def test_read_logs_empty(tmp_path, monkeypatch):
    """无日志文件 → 空列表。"""
    monkeypatch.setenv("MASKIT_AUDIT_LOG", str(tmp_path / "none.log"))
    assert read_logs() == []


def test_audit_log_path_default():
    """默认路径 ~/.maskit/audit.log。"""
    import os
    if "MASKIT_AUDIT_LOG" in os.environ:
        del os.environ["MASKIT_AUDIT_LOG"]
    p = audit_log_path()
    assert str(p).endswith("audit.log")
    assert ".maskit" in str(p)
