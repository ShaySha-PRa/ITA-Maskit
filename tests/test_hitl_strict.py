"""HITL: review manifest, strict fail-closed, table checksum hold, allowlist."""

import json
from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from maskit.cli import app
from maskit.detection.allowlist import Allowlist, AllowlistEntry
from maskit.detection.policy import set_allowlist, set_checksum_policy
from maskit.detection.review import UnresolvedReviewError, fingerprint
from maskit.detection.runctx import begin_run
from maskit.rules.defs import RuleSet, RuleSpec
from maskit.rules.engine import apply_rules
from maskit.rules.loader import load_ruleset
from maskit.text import mask_text_pii

INVALID_ID = "110101199003077777"
VALID_ID = "110101199003077774"
runner = CliRunner()


def setup_function() -> None:
    set_checksum_policy("legacy")
    set_allowlist(None)
    begin_run()


def teardown_function() -> None:
    set_checksum_policy("legacy")
    set_allowlist(None)
    begin_run()


def test_table_review_holds_invalid_id():
    set_checksum_policy("review")
    stats = begin_run()
    rs = load_ruleset()
    subset = RuleSet(
        defs=rs.defs,
        specs=[RuleSpec(column="id_card", rule="id_card", strategy="mask")],
    )
    df = pl.DataFrame({"id_card": [INVALID_ID, VALID_ID]})
    masked, n = apply_rules(df, subset, None)
    rows = masked["id_card"].to_list()
    assert rows[0] == INVALID_ID
    assert rows[1] != VALID_ID
    assert n == 1
    assert stats.review >= 1
    assert INVALID_ID not in json.dumps(stats.review_rows, ensure_ascii=False)


def test_strict_cli_does_not_keep_output(tmp_path: Path):
    src = tmp_path / "ids.csv"
    src.write_text(f"id_card\n{INVALID_ID}\n", encoding="utf-8")
    out = tmp_path / "ids.masked.csv"
    review = tmp_path / "review.jsonl"
    result = runner.invoke(
        app,
        [
            "mask",
            str(src),
            "-o",
            str(out),
            "--checksum-policy",
            "strict",
            "--review-out",
            str(review),
        ],
    )
    assert result.exit_code == 2
    assert not out.exists()
    assert review.exists()
    line = json.loads(review.read_text(encoding="utf-8").splitlines()[0])
    assert line["entity_type"] == "id_card"
    assert line["fingerprint"] == fingerprint(INVALID_ID)
    assert INVALID_ID not in review.read_text(encoding="utf-8")


def test_allowlist_rejects_auto_mask():
    set_checksum_policy("review")
    set_allowlist(
        Allowlist(
            [
                AllowlistEntry(
                    entity_type="id_card",
                    match_mode="exact",
                    value=VALID_ID,
                    scope="document",
                    reason="test",
                    created_at="2026-01-01T00:00:00+00:00",
                )
            ]
        )
    )
    out = mask_text_pii(f"证件 {VALID_ID}", load_ruleset(), None, checksum_policy="review")
    assert VALID_ID in out


def test_unresolved_review_error_is_value_error():
    assert issubclass(UnresolvedReviewError, ValueError)


def test_allowlist_fingerprint_skips_table_mask():
    al = Allowlist()
    al.add_fingerprint("id_card", fingerprint(VALID_ID))
    set_allowlist(al)
    rs = load_ruleset()
    subset = RuleSet(
        defs=rs.defs,
        specs=[RuleSpec(column="id_card", rule="id_card", strategy="mask")],
    )
    df = pl.DataFrame({"id_card": [VALID_ID]})
    masked, n = apply_rules(df, subset, None)
    assert masked["id_card"].to_list()[0] == VALID_ID
    assert n == 0


def test_allowlist_save_load_fingerprint(tmp_path, monkeypatch):
    dest = tmp_path / "allowlist.json"
    monkeypatch.setenv("MASKIT_ALLOWLIST", str(dest))
    from maskit.detection.allowlist import default_allowlist_path

    al = Allowlist()
    al.add_fingerprint("id_card", "abcd1234abcd1234", reason="unit")
    saved = al.save()
    assert saved == dest
    loaded = Allowlist.load(default_allowlist_path())
    assert loaded.allows("id_card", "anything", fingerprint="abcd1234abcd1234")
    assert INVALID_ID not in dest.read_text(encoding="utf-8")


def test_review_manifest_roundtrip_has_no_raw(tmp_path):
    from maskit.detection.review import (
        load_review_manifest,
        row_exposes_raw_value,
        write_review_manifest,
    )

    path = tmp_path / "review.jsonl"
    write_review_manifest(
        path,
        [
            {
                "entity_type": "id_card",
                "fingerprint": fingerprint(INVALID_ID),
                "preview": "11***7",
                "decision": "REVIEW",
            }
        ],
    )
    rows = load_review_manifest(path)
    assert len(rows) == 1
    assert not row_exposes_raw_value(rows[0])
    assert INVALID_ID not in path.read_text(encoding="utf-8")
