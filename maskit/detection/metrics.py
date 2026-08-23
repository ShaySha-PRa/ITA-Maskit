"""Entity-level detection scoring (no transformation)."""

from __future__ import annotations

import re
from collections import defaultdict

from maskit.detection.result import DetectionResult

_COMPACT = re.compile(r"[\s\-]+")


def compact(value: str) -> str:
    return _COMPACT.sub("", value).casefold()


def _same_entity(gold_type: str, gold_value: str, hit: DetectionResult) -> bool:
    if gold_type != hit.entity_type:
        return False
    if gold_value in {hit.original_value, hit.normalized_value}:
        return True
    return compact(gold_value) == compact(hit.normalized_value) or compact(
        gold_value
    ) == compact(hit.original_value)


def pair_hits(
    gold: list[dict],
    pred: list[DetectionResult],
) -> tuple[list[tuple[dict, DetectionResult]], list[dict], list[DetectionResult]]:
    """Greedy 1-1 match. Returns (tp pairs, fn gold, fp pred)."""
    used: set[int] = set()
    tp: list[tuple[dict, DetectionResult]] = []
    fn: list[dict] = []
    for g in gold:
        found = None
        for i, p in enumerate(pred):
            if i in used:
                continue
            if _same_entity(g["type"], g["value"], p):
                found = i
                break
        if found is None:
            fn.append(g)
        else:
            used.add(found)
            tp.append((g, pred[found]))
    fp = [p for i, p in enumerate(pred) if i not in used]
    return tp, fn, fp


def prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fpr": round(fp / (fp + tp), 4) if (fp + tp) else 0.0,
        "fnr": round(fn / (fn + tp), 4) if (fn + tp) else 0.0,
    }


def summarize(
    cases: list[tuple[list[dict], list[DetectionResult]]],
) -> dict:
    """cases: list of (gold entities, predictions) per example."""
    by_type: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    tp = fp = fn = 0
    for gold, pred in cases:
        tps, fns, fps = pair_hits(gold, pred)
        tp += len(tps)
        fp += len(fps)
        fn += len(fns)
        for g, _ in tps:
            by_type[g["type"]]["tp"] += 1
        for g in fns:
            by_type[g["type"]]["fn"] += 1
        for p in fps:
            by_type[p.entity_type]["fp"] += 1
    out = {"overall": prf(tp, fp, fn), "by_type": {}}
    for name, c in sorted(by_type.items()):
        out["by_type"][name] = prf(c["tp"], c["fp"], c["fn"])
    return out
