"""Holdout: same generator, different seed. Must not overfit stress.jsonl."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from maskit.detection.eval_gold import predict_case
from maskit.detection.metrics import summarize
from maskit.rules.loader import load_ruleset

_GEN = Path(__file__).resolve().parents[1] / "scripts" / "gen_stress_gold.py"
_spec = importlib.util.spec_from_file_location("gen_stress_gold", _GEN)
assert _spec and _spec.loader
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_holdout_seed_20260822_zero_errors():
    cases = gen.build_cases(20260822)
    assert len(cases) >= 1500
    rs = load_ruleset()
    paired = [(c.get("entities") or [], predict_case(c, rs)) for c in cases]
    overall = summarize(paired)["overall"]
    assert overall["fp"] == 0, overall
    assert overall["fn"] == 0, overall
