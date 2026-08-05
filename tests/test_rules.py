"""规则引擎测试：每规则 × mask/pseudo 两策略 + 确定性 + 规范化 + domain separation。"""
import pytest

from maskit.rules.defs import BUILTIN_RULE_DEFS, RuleDef
from maskit.rules.engine import (
    _apply_single,
    audit_key,
    hmac_digest,
    pseudo_key,
)


def _rule(name: str) -> RuleDef:
    return RuleDef(name=name, **BUILTIN_RULE_DEFS[name])


# --- mask 策略 ---

@pytest.mark.parametrize("value,expected", [
    ("张伟", "张*"),
    ("Alice Chen", "A*"),
    ("", ""),
])
def test_mask_name(value, expected):
    assert _apply_single(_rule("name"), value, "mask", None) == expected


@pytest.mark.parametrize("value,expected", [
    ("a@b.com", "a***@b.com"),
    ("alice@corp.example", "a***@corp.example"),
])
def test_mask_email(value, expected):
    assert _apply_single(_rule("email"), value, "mask", None) == expected


def test_mask_ip_full_hide():
    """IP 全遮盖：*.*.*.*（评审锁定）。"""
    assert _apply_single(_rule("ip"), "10.1.2.3", "mask", None) == "*.*.*.*"


@pytest.mark.parametrize("value,expected", [
    ("13800000000", "138****0000"),
    ("13800000001", "138****0001"),
])
def test_mask_phone(value, expected):
    assert _apply_single(_rule("phone"), value, "mask", None) == expected


def test_mask_employee_id():
    assert _apply_single(_rule("employee_id"), "EID-7F3A", "mask", None) == "EID-***"


def test_mask_account():
    assert _apply_single(_rule("account"), "zhangsan", "mask", None) == "z***n"


def test_mask_company():
    assert _apply_single(_rule("company"), "亚玛芬体育", "mask", None) == "亚*"


def test_mask_app_version():
    assert _apply_single(_rule("app_version"), "v1.2.3", "mask", None) == "v1.*.*"


# --- pseudo 策略：确定性 ---

def test_pseudo_deterministic_same_input():
    """同一输入 + 同一 pepper → 同一伪名。"""
    r = _rule("email")
    a = _apply_single(r, "alice@corp.example", "pseudo", "pepper-1")
    b = _apply_single(r, "alice@corp.example", "pseudo", "pepper-1")
    assert a == b
    assert a != "alice@corp.example"  # 真被改了


def test_pseudo_cross_table_normalization():
    """跨表规范化：138-0000-0000 与 13800000000 → 同一伪名。"""
    r = _rule("phone")
    a = _apply_single(r, "13800000000", "pseudo", "pepper-1")
    b = _apply_single(r, "138-0000-0000", "pseudo", "pepper-1")
    c = _apply_single(r, "138 0000 0000", "pseudo", "pepper-1")
    assert a == b == c
    assert len(a) == 11  # 保留位数


def test_pseudo_different_pepper_different_result():
    """不同 pepper → 不同伪名（pepper 是密钥）。"""
    r = _rule("email")
    a = _apply_single(r, "alice@corp.example", "pseudo", "pepper-1")
    b = _apply_single(r, "alice@corp.example", "pseudo", "pepper-2")
    assert a != b


def test_pseudo_requires_pepper():
    """pseudo 无 pepper → 报错。"""
    with pytest.raises(ValueError, match="pepper"):
        _apply_single(_rule("email"), "a@b.com", "pseudo", None)


def test_pseudo_employee_id_prefix_preserved():
    """employee_id 伪名化保留前缀。"""
    r = _rule("employee_id")
    out = _apply_single(r, "EID-7F3A", "pseudo", "pepper-1")
    assert out.startswith("EID-")
    assert out != "EID-7F3A"


# --- domain separation ---

def test_domain_separation_keys_differ():
    """伪名化与审计指纹用不同派生 key。"""
    assert pseudo_key("p") != audit_key("p")


def test_hmac_digest_deterministic():
    assert hmac_digest("x", b"key", 8) == hmac_digest("x", b"key", 8)
    assert hmac_digest("x", b"key", 8) != hmac_digest("x", b"other", 8)


# --- 规范化 ---

def test_normalize_phone_dedup():
    from maskit.rules.defs import NORMALIZERS
    assert NORMALIZERS["phone"]("138-0000-0000") == "13800000000"
    assert NORMALIZERS["phone"]("+86 138 0000 0000") == "+8613800000000"


def test_normalize_email_lower():
    from maskit.rules.defs import NORMALIZERS
    assert NORMALIZERS["lower"]("Alice@Corp.Example") == "alice@corp.example"
