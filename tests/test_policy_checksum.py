"""Checksum policy: legacy still auto-applies invalid IDs; review does not."""

from maskit.detection.pipeline import detect_text
from maskit.detection.policy import partition_hits
from maskit.detection.review import fingerprint, hit_to_manifest
from maskit.rules.loader import load_ruleset
from maskit.text import mask_text_pii

INVALID_ID = "110101199003077777"


def test_legacy_still_masks_invalid_id_in_document():
    rs = load_ruleset()
    out = mask_text_pii(f"证件 {INVALID_ID}", rs, None, checksum_policy="legacy")
    assert INVALID_ID not in out


def test_review_policy_does_not_auto_write_invalid_id():
    rs = load_ruleset()
    out = mask_text_pii(f"证件 {INVALID_ID}", rs, None, checksum_policy="review")
    assert INVALID_ID in out
    hits = detect_text(f"证件 {INVALID_ID}", ruleset=rs)
    parts = partition_hits(hits, checksum_policy="review")
    assert parts["REVIEW"]
    row = hit_to_manifest(parts["REVIEW"][0], file="x.pdf", fmt="pdf")
    assert INVALID_ID not in str(row)
    assert row["fingerprint"] == fingerprint(INVALID_ID)


def test_valid_id_auto_applies_under_review_policy():
    rs = load_ruleset()
    valid = "110101199003077774"
    out = mask_text_pii(f"证件 {valid}", rs, None, checksum_policy="review")
    assert valid not in out
