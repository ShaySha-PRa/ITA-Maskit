"""Mapped-column batch HMAC must match the per-cell Python reference."""

from __future__ import annotations

import polars as pl
import pytest

from maskit.demo import generate_demo_data
from maskit.native import native_available, native_unavailable_reason
from maskit.rules.defs import RuleSet
from maskit.rules.engine import _mask_one_cell, apply_rules, render_template
from maskit.rules.loader import load_ruleset
from maskit.rules.matcher import auto_match_columns

PEPPER = "maskit-test-pepper-not-production"


def _pseudo_ruleset(columns: list[str], strategy: str = "pseudo") -> RuleSet:
    rs = load_ruleset()
    specs = auto_match_columns(columns)
    return RuleSet(
        defs=rs.defs,
        specs=[
            type(s)(
                column=s.column,
                rule=s.rule,
                strategy=strategy,
                optional=s.optional,
                bind_mode=s.bind_mode,
                origin=s.origin,
            )
            for s in specs
        ],
    )


def _cell_apply(df: pl.DataFrame, ruleset: RuleSet, pepper: str) -> pl.DataFrame:
    spec_by_col = {s.column: s for s in ruleset.specs}
    cols = {}
    for name in df.columns:
        spec = spec_by_col.get(name)
        rule = ruleset.defs.get(spec.rule) if spec else None
        strategy = spec.strategy if spec else "mask"
        bind_mode = spec.bind_mode if spec else "validate"
        out = []
        for v in df[name].cast(pl.Utf8).to_list():
            cell = _mask_one_cell(
                "" if v is None else v,
                rule,
                strategy,
                [],
                ruleset.defs.get("name"),
                pepper,
                None,
                [],
                (),
                False,
                ruleset=ruleset,
                bind_mode=bind_mode,
                column=name,
                checksum_policy="legacy",
            )
            out.append(cell["masked_value"])
        cols[name] = out
    return pl.DataFrame(cols)


def test_hmac_hex_matches_live_render():
    from maskit.rules.engine import hmac_digest, pseudo_key

    email = "alice@corp.example"
    live = render_template("p{hash:8}@masked.local", email, PEPPER)
    hx = hmac_digest(email, pseudo_key(PEPPER), 64)
    injected = render_template("p{hash:8}@masked.local", email, PEPPER, hmac_hex=hx)
    assert live == injected


def test_apply_rules_batch_matches_cell_python(monkeypatch):
    monkeypatch.setenv("MASKIT_NATIVE", "0")
    df = generate_demo_data(rows=50)
    df = df.with_columns(
        pl.Series("email", df["email"].to_list()[:-1] + [None]),
        pl.lit("=SUM(A1)").alias("formula_like"),
    )
    # formula_like is unmapped; mapped cols use batch
    rs = _pseudo_ruleset([c for c in df.columns if c != "formula_like"])
    batched, n = apply_rules(df, rs, PEPPER, value_scan=False)
    cell = _cell_apply(df.select([c for c in df.columns if c != "formula_like"]), rs, PEPPER)
    for col in cell.columns:
        assert batched[col].to_list() == cell[col].to_list(), col
    assert n > 0


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_apply_rules_native_matches_python(monkeypatch):
    df = generate_demo_data(rows=80)
    rs = _pseudo_ruleset(df.columns)
    monkeypatch.setenv("MASKIT_NATIVE", "0")
    py, n_py = apply_rules(df, rs, PEPPER, value_scan=False)
    monkeypatch.setenv("MASKIT_NATIVE", "1")
    nt, n_nt = apply_rules(df, rs, PEPPER, value_scan=False)
    assert n_py == n_nt
    for col in df.columns:
        assert py[col].to_list() == nt[col].to_list(), col


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_apply_rules_v2_native_matches_python(monkeypatch):
    df = generate_demo_data(rows=40)
    rs = _pseudo_ruleset(df.columns, strategy="pseudo_v2")
    monkeypatch.setenv("MASKIT_NATIVE", "0")
    py, _ = apply_rules(df, rs, PEPPER, value_scan=False)
    monkeypatch.setenv("MASKIT_NATIVE", "1")
    nt, _ = apply_rules(df, rs, PEPPER, value_scan=False)
    for col in df.columns:
        assert py[col].to_list() == nt[col].to_list(), col


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_apply_rules_compare_mode(monkeypatch):
    monkeypatch.setenv("MASKIT_NATIVE", "compare")
    df = generate_demo_data(rows=20)
    rs = _pseudo_ruleset(df.columns)
    apply_rules(df, rs, PEPPER, value_scan=False)
