"""Compare Python reference vs native: correctness + kernel/e2e timing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEPPER = "maskit-test-pepper-not-production"
OUT = ROOT / "benchmark" / "results" / "python_vs_native.json"


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[len(xs) // 2]


def _time(fn, n: int) -> dict:
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return {
        "runs": samples,
        "min": min(samples),
        "median": _median(samples),
        "max": max(samples),
    }


def _pytest(args: list[str], mode: str) -> dict:
    env = os.environ.copy()
    env["MASKIT_NATIVE"] = mode
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-q", "--tb=no", f"--native-mode={mode}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    tail = (proc.stdout or "").strip().splitlines()
    return {
        "returncode": proc.returncode,
        "summary": tail[-1] if tail else "",
        "failed": [ln for ln in tail if ln.startswith("FAILED")][:12],
    }


def _gold_report(mode: str) -> dict:
    import importlib.util

    os.environ["MASKIT_NATIVE"] = mode
    from maskit.detection.eval_gold import GOLD_PATH, predict_case, run_gold
    from maskit.detection.metrics import summarize
    from maskit.rules.loader import load_ruleset

    spec = importlib.util.spec_from_file_location(
        "gen_stress_gold", ROOT / "scripts" / "gen_stress_gold.py"
    )
    assert spec and spec.loader
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    rs = load_ruleset()
    gold = run_gold(GOLD_PATH)["overall"]
    hold = summarize(
        [(c.get("entities") or [], predict_case(c, rs)) for c in gen.build_cases(20260822)]
    )["overall"]
    stress = summarize(
        [(c.get("entities") or [], predict_case(c, rs)) for c in gen.build_cases()]
    )["overall"]
    return {"gold": gold, "holdout": hold, "stress": stress}


def _speedup(py: dict, nt: dict) -> float | None:
    if not nt["median"]:
        return None
    return py["median"] / nt["median"]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from maskit.demo import generate_demo_data
    from maskit.detection.scope import DEFAULT_EMPLOYEE_PREFIXES
    from maskit.io.csvio import mask_csv_file
    from maskit.native import get_backend, native_available
    from maskit.native.fallback import PythonReferenceBackend
    from maskit.rules.defs import RuleSet
    from maskit.rules.loader import load_ruleset
    from maskit.rules.matcher import auto_match_columns

    if not native_available():
        print("native extension missing; build first")
        return 1

    suites = [
        "tests/test_detection.py",
        "tests/test_recognizers_v2.py",
        "tests/test_hmac_v2.py",
        "tests/test_native_parity.py",
        "tests/test_native_dictionary.py",
        "tests/test_native_validators.py",
        "tests/test_native_resolve_detect.py",
        "tests/test_native_column_pseudo.py",
        "tests/test_stress_gold.py",
        "tests/test_holdout.py",
    ]
    out: dict = {
        "native_available": True,
        "pytest_python": _pytest(suites, "python"),
        "pytest_compare": _pytest(
            [
                "tests/test_native_parity.py",
                "tests/test_native_dictionary.py",
                "tests/test_native_validators.py",
                "tests/test_native_resolve_detect.py",
                "tests/test_hmac_v2.py",
            ],
            "compare",
        ),
        "pytest_native_forced": _pytest(
            ["tests/test_stress_gold.py", "tests/test_holdout.py", "tests/test_recognizers_v2.py"],
            "native",
        ),
    }

    os.environ["MASKIT_NATIVE"] = "0"
    out["metrics_python"] = _gold_report("0")
    out["metrics_native"] = _gold_report("1")

    py = PythonReferenceBackend()
    nt = get_backend("native")
    values = [f"138{str(i).zfill(8)}" for i in range(100_000)]
    names = ["张伟", "李娜", "司马光", "司马光华", "王芳", "刘洋"] * 800
    text = ("经办张伟复核，联系人司马光华，手机 13800138000。" * 400)
    texts = [text] * 200
    phones = ["13800138000", "2019.06.22", "010-12989966", "１３８００１３８０００"] * 8000
    ids = ["110101199003077774", "110101199003077777", "110101 19900307 7774"] * 8000

    benches = {}
    benches["hmac_100k"] = {
        "python": _time(lambda: py.hash_batch(values, PEPPER, "v1", length=8), 3),
        "native": _time(lambda: nt.hash_batch(values, PEPPER, "v1", length=8), 3),
    }
    benches["person_list_200x"] = {
        "python": _time(lambda: py.match_person_list_batch(texts, names), 3),
        "native": _time(lambda: nt.match_person_list_batch(texts, names), 3),
    }
    benches["phone_32k"] = {
        "python": _time(lambda: [py.is_phone_value(v, column_mode=True) for v in phones], 3),
        "native": _time(lambda: [nt.is_phone_value(v, column_mode=True) for v in phones], 3),
    }
    benches["id_checksum_24k"] = {
        "python": _time(lambda: [py.id_card_checksum_ok(v) for v in ids], 3),
        "native": _time(lambda: [nt.id_card_checksum_ok(v) for v in ids], 3),
    }
    col_vals = ["13800138000", "2019.06.22", "EID-10001", "v1.2.3"] * 2500
    benches["detect_column_phone_10k"] = {
        "python": _time(
            lambda: py.detect_column_batch(col_vals, "phone", DEFAULT_EMPLOYEE_PREFIXES), 3
        ),
        "native": _time(
            lambda: nt.detect_column_batch(col_vals, "phone", DEFAULT_EMPLOYEE_PREFIXES), 3
        ),
    }
    for name, pair in benches.items():
        pair["speedup"] = _speedup(pair["python"], pair["native"])

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

    def csv_run(ruleset, pepper):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.csv"
            dst = Path(td) / "out.csv"
            generate_demo_data(rows=10_000).write_csv(src)
            mask_csv_file(src, dst, ruleset, pepper)

    prev = os.environ.get("MASKIT_NATIVE")
    os.environ["MASKIT_NATIVE"] = "0"
    benches["e2e_10k_mask"] = {"python": _time(lambda: csv_run(rs, None), 3)}
    benches["e2e_10k_pseudo"] = {
        "python": _time(lambda: csv_run(pseudo_rs, PEPPER), 3),
    }
    os.environ["MASKIT_NATIVE"] = "1"
    benches["e2e_10k_mask"]["native"] = _time(lambda: csv_run(rs, None), 3)
    benches["e2e_10k_pseudo"]["native"] = _time(lambda: csv_run(pseudo_rs, PEPPER), 3)
    benches["e2e_10k_mask"]["speedup"] = _speedup(
        benches["e2e_10k_mask"]["python"], benches["e2e_10k_mask"]["native"]
    )
    benches["e2e_10k_pseudo"]["speedup"] = _speedup(
        benches["e2e_10k_pseudo"]["python"], benches["e2e_10k_pseudo"]["native"]
    )
    if prev is None:
        os.environ.pop("MASKIT_NATIVE", None)
    else:
        os.environ["MASKIT_NATIVE"] = prev

    out["benches"] = benches
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
