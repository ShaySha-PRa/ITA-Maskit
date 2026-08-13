# 对抗测试集（traps）

故意设计成审计现场会翻车的形态，用来找误伤和漏检。

| 文件 | 陷阱 |
|------|------|
| `keyword_traps.xlsx` | 列名「地址/单位/版本/联系/编号/账号」绑错规则 |
| `overlap_traps.xlsx` | 张伟达含子串、东方红、v10.20.30.40、JSON/HTML、空格证号、全角邮箱 |
| `layout_traps.xlsx` | Excel 数字 18 位丢精度、重复列名、超长格末尾才出现 PII、标题行当表头 |
| `people.csv` | 张伟 李娜 欧阳修 东方不败（无赵磊） |

```bash
maskit mask testdata/traps/overlap_traps.xlsx --person-list testdata/traps/people.csv -o /tmp/trap.xlsx
```
