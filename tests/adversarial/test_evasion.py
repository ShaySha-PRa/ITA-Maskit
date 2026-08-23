"""Adversarial / evasion cases for detection (false positives and known gaps)."""

from maskit.detection.pipeline import detect_cell, detect_text
from maskit.rules.loader import load_ruleset


def _types(hits) -> set[str]:
    return {h.entity_type for h in hits}


def test_version_string_is_not_ip():
    rs = load_ruleset()
    assert "ip" not in _types(detect_cell("v10.20.30.40", ruleset=rs))
    hits = detect_text("客户端 v10.20.30.40 发布", ruleset=rs)
    assert "ip" not in _types(hits)


def test_date_is_not_ip_or_version_without_column():
    rs = load_ruleset()
    assert detect_cell("2026.08.21", ruleset=rs) == []
    assert detect_cell("2024.1.1", ruleset=rs) == []


def test_decimal_and_formula_not_pii():
    rs = load_ruleset()
    assert detect_cell("2.5", ruleset=rs) == []
    assert detect_cell("=SUM(A1:A9)", ruleset=rs) == []


def test_spaced_id_and_dashed_bank_detected():
    rs = load_ruleset()
    id_hits = detect_cell("身份证 110101 19900307 7777", ruleset=rs)
    assert "id_card" in _types(id_hits)
    bank_hits = detect_cell("卡号 6222-0212-3456-7890", ruleset=rs)
    assert "bank_card" in _types(bank_hits)


def test_fullwidth_email_detected_in_text():
    rs = load_ruleset()
    text = "邮箱：ａｌｉｃｅ＠ｃｏｒｐ．ｅｘａｍｐｌｅ"
    hits = detect_text(text, ruleset=rs)
    assert "email" in _types(hits)


def test_phone_with_spaces_document_path():
    rs = load_ruleset()
    hits = detect_text("手机 138 0013 8000", ruleset=rs)
    assert "phone" in _types(hits)


def test_structured_phone_without_column_not_scanned():
    """防误伤：phone 不进值级白名单（日期/小数）。"""
    rs = load_ruleset()
    assert "phone" not in _types(detect_cell("13800138000", ruleset=rs))


def test_cyrillic_homoglyph_email_not_full_match():
    """西里尔 аlice：不会整串当邮箱；可能误抓后面的 lice@…（ASCII 尾巴）。"""
    rs = load_ruleset()
    hits = detect_text("mail аlice@corp.example", ruleset=rs)
    originals = [h.original_value for h in hits if h.entity_type == "email"]
    assert "аlice@corp.example" not in originals


def test_fullwidth_phone_detected():
    """Python \\d 匹配全角数字，文档路径能扫到全角手机号。"""
    rs = load_ruleset()
    hits = detect_text("电话１３８００１３８０００", ruleset=rs)
    assert "phone" in _types(hits)


def test_document_date_not_phone():
    """收紧后的手机正则不得把日期当电话。"""
    rs = load_ruleset()
    hits = detect_text("截止日期 2026.08.21 请准时。", ruleset=rs)
    assert "phone" not in _types(hits)
    assert "app_version" not in _types(hits)


def test_document_spaced_id_not_stolen_by_phone():
    """空格身份证标 id_card，不被 phone 抢走。"""
    rs = load_ruleset()
    hits = detect_text("身份证 110101 19900307 7777 已归档", ruleset=rs)
    types = _types(hits)
    assert "id_card" in types
    assert "phone" not in types


def test_department_not_company_when_column_mapped():
    rs = load_ruleset()
    hits = detect_cell(
        "财务部",
        ruleset=rs,
        mapped_rule=rs.defs["company"],
    )
    assert hits == []
