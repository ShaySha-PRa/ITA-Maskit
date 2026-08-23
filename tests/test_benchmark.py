"""Labeled detection benchmark: strong-feature precision floor."""

from maskit.detection.eval_gold import run_gold


def test_benchmark_strong_feature_precision_floor():
    """Email/IP 应高精确。人名召回未达标时不得据此引入 NER。"""
    report = run_gold()
    by_type = report["by_type"]
    assert report["n_cases"] >= 20
    assert by_type["email"]["precision"] >= 0.99
    assert by_type["ip"]["precision"] >= 0.99
    assert by_type["ip"]["fp"] == 0


def test_benchmark_overall_has_true_positives():
    report = run_gold()
    assert report["overall"]["tp"] >= 10
