# Stress detection report

日期：2026-08-21。合成集 `benchmark/stress.jsonl`（seed=20260821，**1716** 条）。  
标签是期望行为，不是把当前 bug 标成正确答案。不是现场语料。

生成：`python3 scripts/gen_stress_gold.py`  
评分：`python3 -m maskit.detection.eval_gold benchmark/stress.jsonl --errors 40`

## Overall

| | Precision | Recall | F1 | tp | fp | fn |
|--|-----------|--------|----|----|----|-----|
| **all** | 0.861 | 0.966 | 0.911 | 1827 | 295 | 64 |

## By type

| type | P | R | F1 | tp | fp | fn |
|------|---|---|----|----|----|-----|
| email | 1.000 | 1.000 | 1.000 | 415 | 0 | 0 |
| ip | 1.000 | 1.000 | 1.000 | 330 | 0 | 0 |
| id_card | 1.000 | 1.000 | 1.000 | 360 | 0 | 0 |
| bank_card | 1.000 | 1.000 | 1.000 | 180 | 0 | 0 |
| company | 1.000 | 1.000 | 1.000 | 5 | 0 | 0 |
| name | 0.989 | 0.958 | 0.974 | 92 | 1 | 4 |
| phone | 0.943 | 0.854 | 0.896 | 350 | 21 | 60 |
| employee_id | 0.303 | 1.000 | 0.465 | 30 | 69 | 0 |
| app_version | 0.242 | 1.000 | 0.389 | 65 | 204 | 0 |

## 已收紧的文档 phone：这批里站住了

- `d-neg-date`（100 条）：日期 **0 FP**（不再当 phone / app_version）。
- `d-id-spaced`（50 条）：空格身份证 **全中**，没有被 phone 抢走。
- `d-phone`（150 条 compact/dash/space/+86/全角）：手机号召回完整。

## 仍然误伤 / 漏检（299 条用例有错）

1. **文档金额 → app_version（204 FP）**  
   `金额 2.5` / `0.8` / `13.08` 命中 `v?\d+(\.\d+){1,3}`。`d-mixed` 里 144 条、`d-neg-amount` 40 条、`d-appver-date-amount` 20 条。
2. **文档座机漏检，并被当成工号（60 FN phone + 60 FP employee_id）**  
   `010-12989966` / `0755-5707154` 不匹配大陆 11 位手机正则，却匹配 `EID-\d{4,}` 那种 `[A-Za-z0-9]+-\d{4,}`。
3. **列名叫电话、格子是日期（21 FP phone）**  
   YAML 宽规则整格 fullmatch。文档路径已收紧，**列映射没改**。
4. **标准号当工号（9 FP employee_id）**  
   `ISO-8601`、`RFC-2119`、`CVE-2024`、`JIRA-1001` 等。`UTF-16` 因不足 4 位数字幸免。
5. **二字清单名 + 下一汉字（4 FN name）**  
   `经办张伟复核` 被「张伟达」防误伤逻辑跳过（`张伟`+`复` 像三字名）。三字及以上清单名不受影响。
6. **三字清单切四字（1 FP name）**  
   `司马光` 切 `司马光华`。与现有 xfail 同类。

## 不是本集证明的

- 没有真实 PDF/OCR/邮件文件级标注。Excel 样本在 `testdata/stress/notes.xlsx`（400 行混乱备注 + 电话列塞日期），用于手工抽查，不计入上表。
- 强特征（email / IP / 身份证 / 银行卡）在这 1716 条上 P=R=1.0，不能外推到现场格式。
