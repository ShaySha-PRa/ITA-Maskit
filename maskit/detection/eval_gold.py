"""Load benchmark/gold.jsonl and run detect_cell / detect_text."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from maskit.detection.metrics import pair_hits, summarize
from maskit.detection.pipeline import detect_cell, detect_text
from maskit.rules.loader import load_ruleset

GOLD_PATH = Path(__file__).resolve().parents[2] / "benchmark" / "gold.jsonl"


def load_gold(path: Path = GOLD_PATH) -> list[dict]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    return cases


def predict_case(case: dict, ruleset) -> list:
    person_list = set(case["person_list"]) if case.get("person_list") else None
    mapped = None
    if case.get("mapped_rule"):
        mapped = ruleset.defs.get(case["mapped_rule"])
    if case["path"] == "structured":
        return detect_cell(
            case["text"],
            ruleset=ruleset,
            mapped_rule=mapped,
            person_list=person_list,
        )
    return detect_text(
        case["text"],
        ruleset=ruleset,
        person_list=person_list,
        scan_names=bool(case.get("scan_names")),
    )


def format_report(report: dict) -> str:
    def row(name: str, m: dict) -> str:
        return (
            f"{name:<22} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} "
            f"tp={m['tp']} fp={m['fp']} fn={m['fn']}"
        )

    lines = [f"cases: {report['n_cases']}", row("OVERALL", report["overall"])]
    for name, m in report["by_type"].items():
        lines.append(row(name, m))
    if report.get("by_family"):
        lines.append("FAMILY")
        for name, m in report["by_family"].items():
            if m["fp"] or m["fn"]:
                lines.append(row(name, m))
    return "\n".join(lines)


def collect_errors(path: Path = GOLD_PATH) -> list[dict]:
    ruleset = load_ruleset()
    errors = []
    for case in load_gold(path):
        pred = predict_case(case, ruleset)
        _tp, fn, fp = pair_hits(case.get("entities") or [], pred)
        if not fn and not fp:
            continue
        errors.append(
            {
                "id": case.get("id"),
                "family": case.get("family"),
                "path": case.get("path"),
                "text": case.get("text"),
                "gold": case.get("entities") or [],
                "fn": fn,
                "fp": [
                    {"type": p.entity_type, "value": p.original_value, "reason": p.reason}
                    for p in fp
                ],
            }
        )
    return errors


def run_gold(path: Path = GOLD_PATH) -> dict:
    ruleset = load_ruleset()
    gold_cases = load_gold(path)
    paired = []
    by_family: dict[str, list] = defaultdict(list)
    for case in gold_cases:
        pred = predict_case(case, ruleset)
        gold = case.get("entities") or []
        paired.append((gold, pred))
        family = case.get("family") or case.get("id", "ungrouped").rsplit("-", 1)[0]
        by_family[family].append((gold, pred))
    report = summarize(paired)
    report["n_cases"] = len(gold_cases)
    report["by_family"] = {
        name: summarize(items)["overall"] for name, items in sorted(by_family.items())
    }
    return report


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Score detection against a gold jsonl")
    parser.add_argument("gold", nargs="?", default=str(GOLD_PATH))
    parser.add_argument("--errors", type=int, default=0, help="print up to N error cases")
    args = parser.parse_args()
    path = Path(args.gold)
    print(format_report(run_gold(path)))
    if args.errors:
        errs = collect_errors(path)
        print(f"\nerrors: {len(errs)} (showing {min(args.errors, len(errs))})")
        for item in errs[: args.errors]:
            print(
                f"- {item['id']} family={item['family']}\n"
                f"  text={item['text'][:120]!r}\n"
                f"  fn={item['fn']}\n"
                f"  fp={item['fp']}"
            )
    sys.exit(0)
