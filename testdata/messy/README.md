# 混乱布局测试数据（messy）

用来压当前表格引擎：列映射先校验、整格值级检测、格内强特征扫描、人员清单。

## 文件

| 文件 | 说明 |
|------|------|
| `messy_mixed.xlsx` | 混乱备注 / 嵌套正文 / 无语义列名 / 标题错位 / 选手收入 |
| `messy_vs_clean.xlsx` | 规整列 vs 混乱散落 |
| `in_cell_stress.xlsx` | 格内多 PII、粘连邮箱、手机号句中、版本/日期防误伤 |
| `false_positives.xlsx` | 「备注邮箱」列名过宽、排除词整格 |
| `scatter.xlsx` | 20 行敏感值轮转落在 A–H 列 |
| `audit_pack.xlsx` | 访谈纪要 / 附件清单 / 抽样表 |
| `scatter.csv` | CSV 对照 |
| `people.csv` | 清单内：张伟/李娜/欧阳修/司马光/东方不败/王芳/陈静 |

## 建议命令

```bash
maskit mask testdata/messy/in_cell_stress.xlsx --person-list testdata/messy/people.csv -o /tmp/out.xlsx
```

## 预期（有人员清单）

- 格内邮箱 / IP / 身份证 / 银行卡 → 遮
- 格内清单人名 → 遮；清单外赵磊/黄敏/周杰 → 不遮
- 句中手机号 → **不遮**（弱特征，防误伤）
- `无` / `策划部` 即使列名叫备注邮箱 → **不套** email 模板
- `2.5` / `2024.1.1` / `=SUM(...)` → 不遮
