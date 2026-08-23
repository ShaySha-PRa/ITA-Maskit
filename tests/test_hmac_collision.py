"""HMAC truncation collision / determinism checks (Phase 5)."""

from maskit.rules.defs import BUILTIN_RULE_DEFS, RuleDef
from maskit.rules.engine import _apply_single, hmac_digest, pseudo_key


def test_ten_thousand_phones_unique_under_8hex():
    """2^32 空间下 1 万样本期望碰撞 ≪ 1；若失败说明截断过短已在小样本暴露。"""
    rule = RuleDef(name="phone", **BUILTIN_RULE_DEFS["phone"])
    pepper = "bench-pepper"
    outs = [
        _apply_single(rule, f"138{str(i).zfill(8)}", "pseudo", pepper) for i in range(10_000)
    ]
    assert len(outs) == len(set(outs))


def test_same_canonical_phone_collapses():
    rule = RuleDef(name="phone", **BUILTIN_RULE_DEFS["phone"])
    a = _apply_single(rule, "138-0000-0001", "pseudo", "p")
    b = _apply_single(rule, "13800000001", "pseudo", "p")
    c = _apply_single(rule, "138 0000 0001", "pseudo", "p")
    assert a == b == c


def test_hash8_space_is_32_bits():
    h = hmac_digest("x", pseudo_key("p"), 8)
    assert len(h) == 8
    int(h, 16)  # hex
