# Detection benchmark

Hand-labeled synthetic gold set. Not a production corpus.

```bash
python benchmark/run.py
# or
python -m maskit.detection.eval_gold
```

Gold: `benchmark/gold.jsonl`（手标小集）。压力集：`benchmark/stress.jsonl`（`scripts/gen_stress_gold.py`）。

```bash
python3 -m maskit.detection.eval_gold benchmark/stress.jsonl --errors 40
```

报告：`benchmark/stress-report.md`。评分：`maskit/detection/metrics.py`。

Do not claim “better detection” without this report moving.
