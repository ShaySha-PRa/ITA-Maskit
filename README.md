# ITA-maskit · 高性能数据脱敏 CLI

审计场景的数据脱敏工具：把敏感字段**遮盖**（mask）或**确定性伪名化**（pseudo），支持数据驱动规则配置，规则变化只需改 YAML、不动代码。

> 审计要求每年都在变 —— ITA-maskit 把「脱敏规则」做成数据：新增字段类型 / 调整遮盖策略，编辑一段 YAML 即可，无需发版。规则带版本号，审计可追溯「哪版规则产出哪个结果」。

## 核心能力

| 能力 | 说明 |
|------|------|
| **8 类内置敏感字段** | 姓名、邮箱、IP（全遮盖 `*.*.*.*`）、手机号、工号、账号、公司名、软件版本号 |
| **两种脱敏策略** | `mask`（部分遮盖，保留可读性）+ `pseudo`（确定性伪名化） |
| **确定性伪名化** | 同一敏感值在不同文件/批次映射到**同一伪名**（HMAC + pepper），保留跨表关联、审计可追溯 |
| **数据驱动规则** | YAML 覆盖/新增规则（正则 + 遮盖模板 + 版本号），响应每年变化的合规要求 |
| **高性能** | Polars（Rust 内核），100 万行全 mask 约 **4 秒**，含伪名化约 **10 秒** |
| **审计日志** | JSONL 记录操作、规则版本、pepper 指纹（不存明文，domain separation） |

## 快速开始

```bash
# 安装
pip install -e .

# 1) 生成演示数据（10 万行，含各类敏感字段）
maskit demo --rows 100000

# 2) 写一个规则文件（phone 用伪名化，其余遮盖）
cat > demo-rules.yaml << 'EOF'
rules:
  - column: phone
    rule: phone
    strategy: pseudo
  - column: name
    rule: name
    strategy: mask
  - column: email
    rule: email
    strategy: pseudo
  - column: ip
    rule: ip
    strategy: mask
  - column: company
    rule: company
    strategy: mask
  - column: app_version
    rule: app_version
    strategy: mask
EOF

# 3) 脱敏（pseudo 需要 pepper 密钥）
maskit mask demo_data.csv --rules demo-rules.yaml --pepper <你的密钥> -o out.csv

# 4) 查看审计日志
maskit audit
```

**演示确定性**：跑两次 `maskit mask`（同一输入、同一 pepper），输出**逐字节一致**——这是「跨文件可关联」的保证。

## 命令

| 命令 | 说明 |
|------|------|
| `maskit mask <in.csv> [--rules r.yaml] [--pepper KEY] [-o out.csv]` | 脱敏 CSV（缺省用内置默认规则集，全部 mask） |
| `maskit demo [--rows N] [--seed N]` | 生成确定性演示数据 |
| `maskit rules list` | 列出可用规则 |
| `maskit audit [--limit N]` | 查看审计日志 |

## 规则配置（数据驱动）

**两段式 schema**：`rule_defs` 定义规则，`rules` 做列映射。

```yaml
# ① 规则定义（可覆盖内置 / 新增自定义）
rule_defs:
  ip:
    version: "1.1"
    match: '^\d{1,3}(\.\d{1,3}){3}$'
    mask: '*.*.*.*'              # 全遮盖（IP 要求全隐藏）
    pseudo: 'IP-{hash:8}'
  tin:                            # 新增：税务登记号（明年要求）
    version: "1.0"
    match: '^[A-Z0-9]{15,18}$'
    mask: '***-{tail:4}'
    pseudo: 'TIN-{hash:8}'
# ② 列映射
rules:
  - column: ip
    rule: ip
    strategy: mask
  - column: tin
    rule: tin
    strategy: pseudo
```

**模板占位符**：`{hash:8}`（确定性哈希）、`{first}`/`{last}`、`{head:3}`/`{tail:4}`、`{prefix}`、`{digits}`、`{major}`、`{domain}`。

**规则带版本**：每次运行把规则集版本写进审计日志，可追溯。

## 安全边界

- **pepper 是密钥**：pseudo 策略必须提供 `--pepper` 或 `MASKIT_PEPPER` 环境变量，缺失即报错（不静默）。CLI 传参仅用于演示，生产用环境变量（避免 shell 历史/`ps` 泄露）。
- **pepper 轮换 = 全部历史伪名失效**：换 pepper 后跨表关联断裂，须同步重脱敏。建议视为长期密钥。
- **join/关联键列必须用 pseudo**：用 mask 会破坏关联性。
- **确定性伪名化是「用于测试的脱敏」**，不是合规控制（频率分析可破解单一替换）。生产合规请咨询安全团队。
- **审计指纹 domain separation**：伪名化与审计指纹用不同派生 key，防交叉泄露。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 1 | 运行失败（I/O、编码），保留 traceback |
| 2 | 用户错误（缺 pepper/缺列/非法 YAML），一行清晰错误，无 traceback |

## 开发

```bash
pip install -e ".[dev]"
pytest            # 48 个测试，覆盖确定性/边缘/性能
ruff check .      # 代码规范
```

## 性能

| 场景 | 耗时 |
|------|------|
| 100 万行，全 mask（8 列） | ~4 秒（27 万行/秒） |
| 100 万行，2 pseudo + 4 mask | ~10 秒（10 万行/秒） |

参考机型：2020 年后普通笔记本。Polars 惰性处理，内存占用低。

## 免责声明

本工具用于测试/演示数据脱敏与审计工作流辅助。请勿用于生产环境敏感数据的合规脱敏，除非已由安全/合规团队评估。
