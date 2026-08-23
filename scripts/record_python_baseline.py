"""Record immutable Python-reference metrics before any native migration.

Usage (from worktree root, with the package installed):

    python scripts/record_python_baseline.py
    python scripts/record_python_baseline.py --profile-only
"""
from __future__ import annotations

import cProfile
import importlib.util
import io
import json
import os
import pstats
import resource
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmark" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def _maxrss_kb() -> int | None:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss = int(usage.ru_maxrss)
    if sys.platform == "darwin":
        return rss // 1024
    return rss


def _time_runs(fn, n: int = 5) -> dict:
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    samples.sort()
    return {
        "runs": samples,
        "min": samples[0],
        "median": samples[len(samples) // 2],
        "max": samples[-1],
    }


def _pytest_summary() -> dict:
    env = os.environ.copy()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    tail = (proc.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else ""
    return {
        "returncode": proc.returncode,
        "summary": summary,
        "stderr_tail": (proc.stderr or "").strip().splitlines()[-8:],
    }


def _ruff() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "").strip().splitlines()[-5:],
    }


def _gold_reports() -> dict:
    from maskit.detection.eval_gold import GOLD_PATH, run_gold
    from maskit.detection.metrics import summarize
    from maskit.detection.eval_gold import predict_case
    from maskit.rules.loader import load_ruleset

    spec = importlib.util.spec_from_file_location(
        "gen_stress_gold", ROOT / "scripts" / "gen_stress_gold.py"
    )
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    gold = run_gold(GOLD_PATH)
    stress_cases = gen.build_cases()
    holdout_cases = gen.build_cases(20260822)
    rs = load_ruleset()

    def score(cases):
        paired = [(c.get("entities") or [], predict_case(c, rs)) for c in cases]
        return summarize(paired)

    stress = score(stress_cases)
    holdout = score(holdout_cases)
    return {
        "gold": {
            "n_cases": gold["n_cases"],
            **gold["overall"],
            "by_type": gold["by_type"],
        },
        "stress": {
            "n_cases": len(stress_cases),
            **stress["overall"],
            "by_type": stress["by_type"],
        },
        "holdout": {
            "n_cases": len(holdout_cases),
            "seed": 20260822,
            **holdout["overall"],
            "by_type": holdout["by_type"],
        },
    }


def _csv_bench(rows: int, pepper: str | None, force_pseudo: bool, repeats: int) -> dict:
    from maskit.demo import generate_demo_data
    from maskit.io.csvio import mask_csv_file
    from maskit.rules.defs import RuleSet
    from maskit.rules.loader import load_ruleset
    from maskit.rules.matcher import auto_match_columns

    ruleset = load_ruleset()
    if force_pseudo:
        specs = auto_match_columns(list(generate_demo_data(rows=1).columns))
        specs = [
            type(s)(
                column=s.column,
                rule=s.rule,
                strategy="pseudo",
                optional=s.optional,
                bind_mode=s.bind_mode,
                origin=s.origin,
            )
            for s in specs
        ]
        ruleset = RuleSet(defs=ruleset.defs, specs=specs)

    def once():
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.csv"
            dst = Path(td) / "out.csv"
            generate_demo_data(rows=rows).write_csv(src)
            mask_csv_file(src, dst, ruleset, pepper)

    return _time_runs(once, n=repeats)


def _hmac_vectors() -> list[dict]:
    from maskit.rules.engine import pseudo_hash, pseudo_hash_v2

    pepper = "maskit-test-pepper-not-production"
    cases = [
        ("", "email"),
        ("13800138000", "phone"),
        ("alice@corp.example", "email"),
        ("张伟", "name"),
        ("a" * 4096, "account"),
        ("EID-7F3A", "employee_id"),
    ]
    out = []
    for value, entity in cases:
        out.append(
            {
                "value": value if len(value) <= 64 else f"<len={len(value)}>",
                "value_len": len(value),
                "entity_type": entity,
                "normalizer_version": "1",
                "pepper": pepper,
                "expected_v1": pseudo_hash(value, pepper, 8),
                "expected_v2": pseudo_hash_v2(value, pepper, entity),
            }
        )
    return out


def _profile_hotspots() -> dict:
    from maskit.demo import generate_demo_data
    from maskit.io.csvio import mask_csv_file
    from maskit.rules.defs import RuleSet
    from maskit.rules.engine import _apply_single, pseudo_hash
    from maskit.rules.loader import load_ruleset
    from maskit.rules.matcher import auto_match_columns
    from maskit.detection.pipeline import detect_cell
    from maskit.detection.pipeline import detect_text as _dt

    rs = load_ruleset()
    specs = auto_match_columns(list(generate_demo_data(rows=1).columns))
    pseudo_rs = RuleSet(
        defs=rs.defs,
        specs=[
            type(s)(
                column=s.column,
                rule=s.rule,
                strategy="pseudo",
                optional=s.optional,
                bind_mode=s.bind_mode,
                origin=s.origin,
            )
            for s in specs
        ],
    )
    phones = [f"138{str(i).zfill(8)}" for i in range(50_000)]
    names = ["张伟", "李娜", "司马光", "司马光华", "王芳"] * 2000
    person_list = {"张伟", "李娜", "司马光", "司马光华", "王芳", "刘洋"}
    long_text = "联系人张伟，邮箱 user@corp.example，手机 13800138000。" * 2000

    def dump(title: str, fn) -> dict:
        pr = cProfile.Profile()
        t0 = time.perf_counter()
        pr.enable()
        fn()
        pr.disable()
        wall = time.perf_counter() - t0
        stream = io.StringIO()
        stats = pstats.Stats(pr, stream=stream).sort_stats("tottime")
        stats.print_stats(20)
        rows = []
        for (filename, lineno, func), cc in stats.stats.items():
            # cc: (cc, nc, tt, ct, callers)
            rows.append(
                {
                    "file": filename,
                    "line": lineno,
                    "func": func,
                    "calls": cc[0],
                    "tottime": cc[2],
                    "cumtime": cc[3],
                }
            )
        rows.sort(key=lambda r: r["tottime"], reverse=True)
        return {
            "title": title,
            "wall_seconds": wall,
            "top": rows[:15],
            "pstats_head": stream.getvalue().splitlines()[:28],
        }

    def mask_10k():
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.csv"
            dst = Path(td) / "out.csv"
            generate_demo_data(rows=10_000).write_csv(src)
            mask_csv_file(src, dst, rs, None)

    def pseudo_10k():
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.csv"
            dst = Path(td) / "out.csv"
            generate_demo_data(rows=10_000).write_csv(src)
            mask_csv_file(src, dst, pseudo_rs, "maskit-test-pepper-not-production")

    def hmac_50k():
        for v in phones:
            pseudo_hash(v, "maskit-test-pepper-not-production", 8)

    def person_list_scan():
        for n in names:
            detect_cell(n, ruleset=rs, person_list=person_list)

    def text_detect():
        _dt(long_text, ruleset=rs, person_list=person_list, scan_names=True)

    return {
        "csv_10k_mask": dump("csv_10k_mask", mask_10k),
        "csv_10k_pseudo": dump("csv_10k_pseudo", pseudo_10k),
        "hmac_50k": dump("hmac_50k", hmac_50k),
        "person_list_10k_cells": dump("person_list_10k_cells", person_list_scan),
        "text_detect_long": dump("text_detect_long", text_detect),
    }


def main() -> int:
    os.chdir(ROOT)
    profile_only = "--profile-only" in sys.argv
    out: dict = {
        "label": "python_reference_baseline",
        "commit": os.environ.get("MASKIT_BASELINE_COMMIT", "7c1518f"),
        "branch": os.environ.get("MASKIT_BASELINE_BRANCH", "feature/native-core-v1"),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "windows_exe_smoke": "not_run_desktop_copy_removed",
        "notes": (
            "Authoritative Python reference before native migration. "
            "Default 10k CSV uses mask (no pepper). Separate pseudo+pepper path recorded."
        ),
    }
    if not profile_only:
        print("=== pytest ===", flush=True)
        out["pytest"] = _pytest_summary()
        print(out["pytest"]["summary"], flush=True)
        print("=== ruff ===", flush=True)
        out["ruff"] = _ruff()
        print("ruff rc=", out["ruff"]["returncode"], flush=True)
        print("=== gold/stress/holdout ===", flush=True)
        out.update(_gold_reports())
        print("gold", out["gold"]["f1"], "stress", out["stress"]["f1"], flush=True)
        print("=== csv benches ===", flush=True)
        out["perf_10k_csv_mask"] = _csv_bench(10_000, None, False, 5)
        out["perf_10k_csv_pseudo"] = _csv_bench(
            10_000, "maskit-test-pepper-not-production", True, 3
        )
        out["perf_100k_csv_mask"] = _csv_bench(100_000, None, False, 1)
        out["hmac_golden_vectors"] = _hmac_vectors()
        out["maxrss_kb_after_benches"] = _maxrss_kb()
        print("10k mask median", out["perf_10k_csv_mask"]["median"], flush=True)
    print("=== cProfile ===", flush=True)
    out["cprofile"] = _profile_hotspots()
    out["maxrss_kb_after_profile"] = _maxrss_kb()
    path = RESULTS / "python_reference_baseline.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
