"""HMAC v2 is opt-in; v1 output must stay byte-identical."""

import hashlib
import hmac

from maskit.rules.defs import RuleSet, RuleSpec
from maskit.rules.engine import _apply_single, pseudo_hash, pseudo_hash_v2, pseudo_key_v2
from maskit.rules.loader import load_ruleset


def test_v1_backward_compatible_hash():
    a = pseudo_hash("13800138000", "pepper-a", 8)
    b = pseudo_hash("13800138000", "pepper-a", 8)
    assert a == b
    assert len(a) == 8
    assert a != pseudo_hash("13800138000", "pepper-b", 8)


def test_v2_determinism_and_entity_separation():
    d1 = pseudo_hash_v2("alice@corp.example", "pepper", "email")
    d2 = pseudo_hash_v2("alice@corp.example", "pepper", "email")
    assert d1 == d2
    assert len(d1) == 24
    other = pseudo_hash_v2("alice@corp.example", "pepper", "account")
    assert other != d1


def test_v2_non_ascii_is_utf8():
    """Windows default encoding is not UTF-8; HMAC must still hash UTF-8 bytes."""
    value = "张伟"
    key = pseudo_key_v2("pepper", "name")
    expected = hmac.new(
        key, f"v2|1|{value}".encode("utf-8"), hashlib.sha256
    ).hexdigest()[:24].upper()
    assert pseudo_hash_v2(value, "pepper", "name") == expected


def test_v2_normalizer_version_separates():
    a = pseudo_hash_v2("x", "p", "email", normalizer_version="1")
    b = pseudo_hash_v2("x", "p", "email", normalizer_version="2")
    assert a != b


def test_apply_v1_unchanged_when_v2_exists():
    rs = load_ruleset()
    email = rs.defs["email"]
    v1 = _apply_single(email, "alice@corp.example", "pseudo", "secret")
    v1b = _apply_single(email, "alice@corp.example", "pseudo", "secret")
    assert v1 == v1b
    v2 = _apply_single(email, "alice@corp.example", "pseudo_v2", "secret")
    assert v2 != v1
    assert "alice" not in v2


def test_v2_digits_not_v1_and_deterministic():
    rs = load_ruleset()
    phone = rs.defs["phone"]
    v1 = _apply_single(phone, "13800138000", "pseudo", "secret")
    v2 = _apply_single(phone, "13800138000", "pseudo_v2", "secret")
    v2b = _apply_single(phone, "13800138000", "pseudo_v2", "secret")
    assert v1.isdigit()
    assert v2.isdigit()
    assert len(v2) == 11
    assert v2 == v2b
    assert v2 != v1


def test_v2_strategy_in_ruleset():
    rs = load_ruleset()
    spec = RuleSpec(column="email", rule="email", strategy="pseudo_v2")
    spec.validate(set(rs.defs))
    RuleSet(defs=rs.defs, specs=[spec])
