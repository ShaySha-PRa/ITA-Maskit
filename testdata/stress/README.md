# 检测压力集（stress）

合成数据，seed=20260821，jsonl 1716 条。标签是期望行为。

| 文件 | 用途 |
|------|------|
| `../../benchmark/stress.jsonl` | detect_cell / detect_text 实体级评测 |
| `../../benchmark/stress-report.md` | 最近一次评分（误伤/漏检） |
| `notes.xlsx` | 400 行混乱备注 + 电话列塞日期 |
| `people.csv` | 人员清单 |

```bash
python3 scripts/gen_stress_gold.py
python3 -m maskit.detection.eval_gold benchmark/stress.jsonl --errors 40
```
