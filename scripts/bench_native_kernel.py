"""Kernel + 10k CSV before/after for the HMAC batch path."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from maskit.demo import generate_demo_data
from maskit.io.csvio import mask_csv_file
from maskit.native import get_backend, native_available
from maskit.native.fallback import PythonReferenceBackend
from maskit.rules.defs import RuleSet
from maskit.rules.loader import load_ruleset
from maskit.rules.matcher import auto_match_columns

ROOT = Path(__file__).resolve().parents[1]
PEPPER = "maskit-test-pepper-not-production"


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


def _pseudo_ruleset() -> RuleSet:
    rs = load_ruleset()
    specs = [
        type(s)(
            column=s.column,
            rule=s.rule,
            strategy="pseudo",
            optional=s.optional,
            bind_mode=s.bind_mode,
            origin=s.origin,
        )
        for s in auto_match_columns(list(generate_demo_data(rows=1).columns))
    ]
    return RuleSet(defs=rs.defs, specs=specs)


def main() -> int:
    values = [f"138{str(i).zfill(8)}" for i in range(100_000)]
    py = PythonReferenceBackend()
    out = {"native_available": native_available()}
    out["python_hmac_100k"] = _time(lambda: py.hash_batch(values, PEPPER, "v1", length=8), 3)
    if native_available():
        nt = get_backend("native")
        t0 = time.perf_counter()
        converted = list(values)
        convert_s = time.perf_counter() - t0
        out["native_hmac_100k"] = _time(
            lambda: nt.hash_batch(converted, PEPPER, "v1", length=8), 3
        )
        out["list_retain_seconds"] = convert_s
        import maskit._native as ext

        out["n7_conversion_100k"] = _time(lambda: ext.batch_identity_size(converted), 5)
        kernel = out["native_hmac_100k"]["median"]
        conv = out["n7_conversion_100k"]["median"]
        out["n7_conversion_share"] = conv / kernel if kernel else None
        out["n7_arrow"] = (
            "skip"
            if (out["n7_conversion_share"] or 0) < 0.30
            else "consider"
        )
        out["kernel_speedup"] = (
            out["python_hmac_100k"]["median"] / out["native_hmac_100k"]["median"]
        )
        phones = ["13800138000", "2019.06.22", "010-12989966"] * 10_000
        out["python_phone_30k"] = _time(
            lambda: [py.is_phone_value(v, column_mode=True) for v in phones], 3
        )
        out["native_phone_30k"] = _time(
            lambda: [nt.is_phone_value(v, column_mode=True) for v in phones], 3
        )

    pseudo_rs = _pseudo_ruleset()

    def e2e():
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.csv"
            dst = Path(td) / "out.csv"
            generate_demo_data(rows=10_000).write_csv(src)
            mask_csv_file(src, dst, pseudo_rs, PEPPER)

    prev = os.environ.get("MASKIT_NATIVE")
    os.environ["MASKIT_NATIVE"] = "0"
    out["e2e_10k_pseudo_python"] = _time(e2e, 3)
    if native_available():
        os.environ["MASKIT_NATIVE"] = "1"
        out["e2e_10k_pseudo_native"] = _time(e2e, 3)
        out["e2e_speedup"] = (
            out["e2e_10k_pseudo_python"]["median"] / out["e2e_10k_pseudo_native"]["median"]
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.csv"
            py_out = Path(td) / "py.csv"
            nt_out = Path(td) / "nt.csv"
            generate_demo_data(rows=200).write_csv(src)
            os.environ["MASKIT_NATIVE"] = "0"
            mask_csv_file(src, py_out, pseudo_rs, PEPPER)
            os.environ["MASKIT_NATIVE"] = "1"
            mask_csv_file(src, nt_out, pseudo_rs, PEPPER)
            import polars as pl

            assert pl.read_csv(py_out).equals(pl.read_csv(nt_out))
            out["e2e_200_row_parity"] = True
    if prev is None:
        os.environ.pop("MASKIT_NATIVE", None)
    else:
        os.environ["MASKIT_NATIVE"] = prev
    out["note"] = (
        "Mapped pseudo columns use hash_batch + template render; "
        "mask columns still use map_elements."
    )
    path = ROOT / "benchmark" / "results" / "native_kernel_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
