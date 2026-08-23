"""Detection layer: DetectionResult, checksum, merge, recognizers, engine compat."""

from __future__ import annotations

import polars as pl
import pytest

from maskit.detection.base import DetectContext
from maskit.detection.checksum import (
    ChecksumRecognizer,
    id_card_checksum_ok,
    luhn_ok,
)
from maskit.detection.column import ColumnRecognizer
from maskit.detection.dictionary import DictionaryRecognizer
from maskit.detection.merge import ConflictResolver
from maskit.detection.pipeline import detect_cell, detect_text
from maskit.detection.regex import RegexRecognizer
from maskit.detection.registry import RecognizerRegistry
from maskit.detection.result import DetectionResult, confidence_band
from maskit.rules.defs import RuleSet
from maskit.rules.engine import apply_rules
from maskit.rules.loader import load_ruleset

VALID_ID = "110101199003077774"  # GB 11643 check digit
INVALID_ID = "110101199003077777"  # used throughout existing fixtures
VALID_VISA = "4111111111111111"
INVALID_BANK = "6222021234567890"


def _ctx(**kwargs) -> DetectContext:
    rs = load_ruleset()
    return DetectContext(ruleset=rs, **kwargs)


def test_confidence_band_thresholds():
    assert confidence_band(1.0) == "HIGH"
    assert confidence_band(0.90) == "HIGH"
    assert confidence_band(0.89) == "MEDIUM"
    assert confidence_band(0.60) == "MEDIUM"
    assert confidence_band(0.59) == "LOW"
    assert confidence_band(0.0) == "LOW"


def test_detection_result_rejects_bad_confidence():
    with pytest.raises(ValueError, match="confidence"):
        DetectionResult(
            entity_type="email",
            original_value="a@b.com",
            normalized_value="a@b.com",
            confidence=1.5,
            recognizer="regex",
            reason="x",
            source="cell",
        )


def test_detection_result_band_auto():
    r = DetectionResult(
        entity_type="email",
        original_value="a@b.com",
        normalized_value="a@b.com",
        confidence=0.92,
        recognizer="regex",
        reason="regex",
        source="cell",
    )
    assert r.band == "HIGH"


def test_id_card_checksum_valid_and_invalid():
    assert id_card_checksum_ok(VALID_ID)
    assert not id_card_checksum_ok(INVALID_ID)
    assert not id_card_checksum_ok("123")
    spaced = VALID_ID[:6] + " " + VALID_ID[6:14] + " " + VALID_ID[14:]
    assert id_card_checksum_ok(spaced)


def test_luhn_valid_and_invalid():
    assert luhn_ok(VALID_VISA)
    assert not luhn_ok(INVALID_BANK)
    assert not luhn_ok("123")


def test_checksum_recognizer_confidence():
    rec = ChecksumRecognizer()
    ctx = _ctx()
    hits = rec.detect(f"id {VALID_ID} fake {INVALID_ID}", ctx)
    by_val = {h.original_value: h for h in hits if h.entity_type == "id_card"}
    assert by_val[VALID_ID].confidence == 1.0
    assert by_val[VALID_ID].band == "HIGH"
    assert by_val[INVALID_ID].confidence == 0.45
    assert by_val[INVALID_ID].band == "LOW"


def test_conflict_resolver_longer_span_wins():
    a = DetectionResult(
        entity_type="id_card",
        original_value="110101 19900307 7774",
        normalized_value=VALID_ID,
        confidence=0.80,
        recognizer="regex",
        reason="variant",
        source="cell",
        start=0,
        end=20,
    )
    b = DetectionResult(
        entity_type="id_card",
        original_value=VALID_ID,
        normalized_value=VALID_ID,
        confidence=1.0,
        recognizer="checksum",
        reason="compact",
        source="cell",
        start=0,
        end=18,
    )
    kept = ConflictResolver().merge([a, b], text_len=20)
    assert len(kept) == 1
    assert kept[0].original_value == a.original_value


def test_conflict_resolver_same_span_higher_confidence():
    low = DetectionResult(
        entity_type="id_card",
        original_value=INVALID_ID,
        normalized_value=INVALID_ID,
        confidence=0.45,
        recognizer="checksum",
        reason="fail",
        source="cell",
        start=0,
        end=18,
    )
    high = DetectionResult(
        entity_type="id_card",
        original_value=INVALID_ID,
        normalized_value=INVALID_ID,
        confidence=0.80,
        recognizer="regex",
        reason="regex",
        source="cell",
        start=0,
        end=18,
    )
    kept = ConflictResolver().merge([low, high], text_len=18)
    assert len(kept) == 1
    assert kept[0].recognizer == "regex"


def test_registry_runs_regex_and_checksum():
    ctx = _ctx()
    reg = RecognizerRegistry([RegexRecognizer("search"), ChecksumRecognizer()])
    hits = reg.detect(f"contact {VALID_ID}", ctx)
    types = {h.entity_type for h in hits}
    assert "id_card" in types


def test_regex_fullmatch_picks_id_not_plain_text():
    rec = RegexRecognizer("fullmatch")
    ctx = _ctx()
    assert rec.detect(INVALID_ID, ctx)[0].entity_type == "id_card"
    assert rec.detect("普通文本", ctx) == []


def test_column_recognizer_skips_department_on_company():
    rs = load_ruleset()
    rule = rs.defs["company"]
    ctx = DetectContext(ruleset=rs, column="单位", mapped_rule=rule)
    rec = ColumnRecognizer()
    assert rec.detect("财务部", ctx) == []
    hits = rec.detect("亚玛芬体育", ctx)
    assert len(hits) == 1
    assert hits[0].recognizer == "column"
    assert hits[0].confidence >= 0.90


def test_dictionary_exact_person_list_and_heuristic():
    rs = load_ruleset()
    rec = DictionaryRecognizer("exact")
    listed = rec.detect("李娜", DetectContext(ruleset=rs, person_list={"李娜"}))
    assert listed[0].confidence >= 0.95
    heuristic = rec.detect("张伟", DetectContext(ruleset=rs, person_list=None))
    assert heuristic[0].band == "MEDIUM"
    skipped = rec.detect("赵磊", DetectContext(ruleset=rs, person_list={"李娜"}))
    assert skipped == []


def test_detect_cell_does_not_mask_formula_or_version_lookalike():
    rs = load_ruleset()
    assert detect_cell("=SUM(A1:A2)", ruleset=rs) == []
    hits = detect_cell("客户端 v10.20.30.40 发布", ruleset=rs)
    assert all("v10.20.30.40" not in h.original_value for h in hits)


def test_detect_text_skips_ip_shaped_phone():
    rs = load_ruleset()
    hits = detect_text("客户端 v10.20.30.40 发布 10.1.2.3", ruleset=rs)
    originals = [h.original_value for h in hits]
    assert "10.1.2.3" in originals
    assert "v10.20.30.40" not in originals


def test_apply_rules_still_masks_fixture_invalid_id():
    """Checksum LOW must not drop historical regex hits (Phase 4 compat)."""
    rs = RuleSet(defs=load_ruleset().defs, specs=[])
    df = pl.DataFrame({"证件": [INVALID_ID, "普通文本"]})
    masked, count = apply_rules(df, rs, None)
    assert INVALID_ID not in masked["证件"].to_list()[0]
    assert count == 1


def test_apply_rules_in_cell_email_unchanged_shape():
    rs = RuleSet(defs=load_ruleset().defs, specs=[])
    df = pl.DataFrame({"正文": ["联系邮箱 alice@corp.example，请审批。"]})
    masked, count = apply_rules(df, rs, None)
    assert "alice@corp.example" not in masked["正文"].to_list()[0]
    assert "a***@corp.example" in masked["正文"].to_list()[0]
    assert count == 1
