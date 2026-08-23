"""压力标注集：锁定已修的日期/空格证号，不要求整集 F1=1。"""
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


def _by_family(cases, ruleset):
    grouped: dict[str, list] = {}
    for case in cases:
        pred = predict_case(case, ruleset)
        grouped.setdefault(case["family"], []).append((case.get("entities") or [], pred))
    return grouped


def test_stress_known_families_zero_errors():
    cases = gen.build_cases()
    rs = load_ruleset()
    grouped = _by_family(cases, rs)
    for fam in (
        "d-neg-date",
        "d-neg-amount",
        "d-landline",
        "d-id-spaced",
        "d-neg-lookalike-eid",
        "s-mapped-phone-date",
        "d-name-3cut",
        "d-name-list",
        "d-phone",
    ):
        m = summarize(grouped[fam])["overall"]
        assert m["fp"] == 0 and m["fn"] == 0, (fam, m)


def test_stress_email_ip_precision_floor():
    cases = gen.build_cases()
    rs = load_ruleset()
    paired = [(c.get("entities") or [], predict_case(c, rs)) for c in cases]
    by_type = summarize(paired)["by_type"]
    assert by_type["email"]["precision"] >= 0.99
    assert by_type["ip"]["fp"] == 0
