# 第二轮复杂验证集（v2）

与 testdata/traps、testdata/messy 错开人名和场景，用来复验上一轮误伤/漏检修复。

人员清单：司马光 上官婉儿 诸葛孔明 刘洋 王芳 Alice Chen（无赵磊）

```bash
python3 scripts/gen_v2_testdata.py
python3 -m pytest tests/test_v2_testdata.py -v
```
