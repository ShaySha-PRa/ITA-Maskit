# ITA-maskit V5 · 高性能数据脱敏工具

审计场景的数据脱敏工具：把敏感字段**遮盖**（mask）或**确定性伪名化**（pseudo），支持数据驱动规则配置，规则变化只需改 YAML、不动代码。**全程本地运行，数据不出机器。** 提供 CLI 和 **Windows 桌面 GUI** 两种形态。

> 审计要求每年都在变 —— ITA-maskit 把「脱敏规则」做成数据：新增字段类型 / 调整遮盖策略，编辑一段 YAML 即可，无需发版。规则带版本号，审计可追溯「哪版规则产出哪个结果」。

## 核心能力

| 能力 | 说明 |
|------|------|
| **Windows 桌面 GUI** | 拖拽文件 → 脱敏 → 实时显示处理/脱敏/进度，面向不懂代码的审计人员 |
| **8 类内置敏感字段** | 姓名、邮箱、IP（全遮盖 `*.*.*.*`）、手机号、工号、账号、公司名、软件版本号 |
| **10 种文件格式** | CSV / Excel / JSON / JSONL / 邮件(.eml) / Outlook(.msg) / PDF / Word(.docx) |
| **双引擎架构** | 表格引擎（按列脱敏）+ 文本引擎（全文 PII 扫描） |
| **两种脱敏策略** | `mask`（部分遮盖，保留可读性）+ `pseudo`（确定性伪名化） |
| **确定性伪名化** | 同一敏感值在不同文件/批次映射到**同一伪名**（HMAC + pepper），保留跨表关联、审计可追溯 |
| **数据驱动规则** | YAML 覆盖/新增规则（正则 + 遮盖模板 + 版本号），响应每年变化的合规要求 |
| **姓名/公司识别** | `--scan-names` 语义前缀 + 词表 + `--person-list` 全量人员清单，纯本地 |
| **图片裁剪脱敏（beta）** | `--image-crop` OCR 定位敏感文字区域并裁剪掉（图变小），需 tesseract |
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

## Windows 桌面 GUI

面向**不懂代码的 IT 审计人员**。拖拽/选择文件 → 点「预验证」看命中 → 点「开始脱敏」→ 实时查看处理/脱敏/进度 → 打开结果文件夹。

### 方式一：直接运行源码（开发/试用）

```bash
git clone git@github.com:ShaySha-PRa/ITA-Maskit.git
cd ITA-Maskit
pip install -e ".[gui,image,llm]"   # 全部依赖（CLI + GUI + 图片 + LLM 规则生成）
python -m maskit.gui_app            # 启动 GUI
# 或用 CLI：maskit mask data.csv --pepper <密钥>
```

### 方式二：打包成 Windows exe（PyInstaller，单文件双击即用）

在 **Windows** 上（已装 Python 3.10+）：

```bash
git clone git@github.com:ShaySha-PRa/ITA-Maskit.git
cd ITA-Maskit
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
# 自动安装依赖 → 打包 → 产出 dist/ITA-Maskit.exe（无需装 Python 即可分发）
```

### 方式三：直接下载 exe（无需自己打包）

仓库 GitHub Actions 在每次 push 到 main 时自动构建 exe：
GitHub → Actions → 最新一次运行 → **Artifacts** → 下载 `ITA-Maskit-exe`，解压即得 `ITA-Maskit.exe`。

> **exe 注意**：
> - 图片脱敏（beta）需额外安装 [tesseract OCR](https://github.com/tesseract-ocr/tesseract) + 中文语言包（exe 未内置）
> - AI 规则生成需设置环境变量 `MASKIT_LLM_API_KEY`

**GUI 功能**：
- 拖拽/浏览选择文件（支持多文件批量）
- 选项：遮盖姓名/公司名、确定性伪名化（需密钥）
- 实时显示：**处理数据数、脱敏数据数、总体进度条**
- 结果列表：文件名/状态/输出路径，一键打开结果文件夹
- 异步处理：大文件不冻结界面
- 规则管理（可视化编辑，描述代替正则）：规则集新建/切换/导入导出、人员清单全覆盖脱敏
- **预验证**：正式脱敏前预览哪些列会被脱敏、命中多少、改了什么样例，未命中列黄标提示（不产出文件）
- **AI 生成规则**：一句话描述 **或** 上传敏感信息规定文档（如 2026 年敏感信息规则，PDF/Word/邮件/文本）→ AI 解析并自动生成对应规则（只发规定/描述，脱敏数据永不出本地）

**性能消耗**（普通办公电脑 4-8GB 内存可流畅运行）：
- CPU 低：仅脱敏瞬间占用（100 万行 ~4 秒）
- 内存中：Polars 惰性处理，处理完释放
- GUI 本身 <50MB

## 支持的文件格式

| 格式 | 扩展名 | 引擎 | 输出 |
|------|--------|------|------|
| CSV | `.csv` | 表格（按列） | CSV |
| Excel | `.xlsx` / `.xls` | 表格（按列） | Excel |
| JSON / JSONL | `.json` / `.jsonl` / `.ndjson` | 表格（按列） | JSONL |
| 邮件 | `.eml` | 文本（全文扫描） | 脱敏 .eml |
| Outlook 邮件 | `.msg` | 文本（全文扫描） | 脱敏 .eml（见局限） |
| PDF | `.pdf` | 文本（全文扫描） | 脱敏 PDF |
| Word | `.docx` | 文本（全文扫描） | 脱敏 .docx |

**表格格式**（CSV/Excel/JSON）按「列」脱敏，规则由 YAML 列映射决定，保留原始 schema 与行序。

**文本格式**（邮件/PDF/Word）没有列，在**全文**中扫描 PII（邮箱/IP/手机号/工号/版本号等有精确正则的字段）并替换，输出保持同格式的脱敏副本（可作审计证据）。

```bash
# 表格格式：按列脱敏（规则由 YAML 决定，支持 pseudo）
maskit mask data.xlsx --rules rules.yaml --pepper <密钥> -o out.xlsx

# 文本格式：全文扫描（--strategy 指定 mask 或 pseudo）
maskit mask mail.eml --strategy mask -o mail_masked.eml
maskit mask report.pdf --strategy pseudo --pepper <密钥> -o report_masked.pdf

# 文本格式 + 识别姓名/公司名（--scan-names，语义前缀+词表，纯本地）
maskit mask mail.eml --scan-names -o mail_masked.eml

# 文本格式 + 全量人员清单（--person-list，动态词表，识别不易判断的人名）
maskit mask mail.eml --scan-names --person-list people.csv -o mail_masked.eml
```

## 姓名/公司名识别（纯本地，零网络）

文本格式默认**不扫描** name/company（它们的匹配正则太宽，`.+` 会误伤普通文字）。需要时用 `--scan-names` 启用，纯本地识别：

- **语义前缀**：`申请人：张伟`、`供应商：亚玛芬体育` → 识别并遮盖
- **内置词表**：审计常见姓名/公司（张伟、亚玛芬体育、MayAir…）
- **全量人员清单**（`--person-list people.csv`）：导入公司全量用户/人员清单（含 `name`/`姓名`/`employee_id` 列），清单里**所有人名**全文匹配脱敏——即使正文里没有「申请人：」这类前缀也能识别

**数据安全**：全部本地正则 + 本地 CSV，**无模型、无网络、数据不出机器**。

## 图片脱敏（beta，默认关闭）

图片里的敏感信息（邮箱/IP/手机号/工号等）用 OCR 定位后**裁剪掉**（图片变小），不是打码遮盖——敏感信息彻底移除。

```bash
# 启用图片裁剪脱敏（beta）
pip install -e ".[image]"        # 安装 Pillow + pytesseract
# 另需手动安装 tesseract 二进制 + 中文语言包（apt install tesseract-ocr tesseract-ocr-chi-sim）

maskit mask screenshot.png --image-crop -o out.png
```

- **默认关闭**：不传 `--image-crop` 时图片格式直接报错提示（beta 阶段不默认处理）
- **数据安全**：tesseract 本地 OCR，数据不出机器
- **已知局限**：裁剪后图片尺寸变小；OCR 识别率受图片质量影响

## LLM 规则生成（可选增强）

审计人员不会写正则/YAML，但**脱敏要求每年都变**。接入大模型 API，把**自然语言描述**或**规则文档**解析成 CLI 可直接用的规则 YAML。

```bash
# 配置（环境变量，支持任意 OpenAI 兼容端点）
export MASKIT_LLM_API_KEY=...          # API key
export MASKIT_LLM_BASE_URL=https://api.openai.com/v1   # 可切通义/DeepSeek/智谱
export MASKIT_LLM_MODEL=gpt-4o-mini    # 或 qwen-plus 等

# 1) 自然语言描述生成规则
maskit rules generate "新增税务登记号脱敏，手机号改为确定性伪名化" -o rules-2027.yaml

# 2) 上传规则文档解析（PDF/Word/邮件/文本）
maskit rules generate --input policy-2027.pdf -o rules-2027.yaml

# 3) 预览不落盘
maskit rules generate "..." --dry-run
```

**功能边界（强约束）**：LLM 是**专用规则生成器**，唯一功能是把脱敏要求解析成规则 YAML。Prompt 层强制——忽略任何规则生成以外的指令、不执行其它任务、输入无法解析时输出空规则文件。

**数据边界（硬约束）**：
- 只有你**主动提供**的「描述/规则文档」发给 LLM
- **脱敏数据（CSV 等）永不进入** LLM 调用
- API key 只从环境变量读，不落盘
- 生成的 YAML 经本地校验（字段完整/策略合法/正则可编译）后才写入，可 `--dry-run` 预览

**合规提示**：规则文档会发给你配置的 LLM 服务商，请确认合规后使用。

## 命令

| 命令 | 说明 |
|------|------|
| `maskit mask <in> [--rules r.yaml] [--pepper KEY] [--strategy mask\|pseudo] [-o out]` | 脱敏任意支持格式 |
| `maskit demo [--rows N] [--seed N]` | 生成确定性演示数据 |
| `maskit rules list` | 列出可用规则 |
| `maskit rules generate "<要求>" [--input doc] [-o out]` | LLM 生成规则 YAML（可选增强） |
| `maskit audit [--limit N]` | 查看审计日志 |

> `--strategy` 仅对文本格式生效；表格格式的策略由各列的 rules.yaml 决定。

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

## 已知局限

- **PDF 是近似保格式**：pypdf 提取文本 + reportlab 重排，会丢失原始排版（字体/表格/图片位置）。如需原样遮盖需 PDF 图层级技术（v3 或独立项目）。
- **name/company 默认不扫文本**：匹配正则太宽，默认跳过防误伤；用 `--scan-names` 启用（语义前缀 + 词表 + 可选人员清单，纯本地）。
- **Excel 支持全部 sheet**：每个 sheet 独立按列脱敏，保留 sheet 结构。
- **.msg 输入输出 .eml**：Outlook `.msg` 是私有 OLE 格式，Python 无库能可靠回写，因此脱敏后输出标准 `.eml`（可打开/转发/作证据）。`.msg→.eml` 的 MIME boundary 每次随机，输出**内容确定但非逐字节一致**。
- **邮件只支持 .eml/.msg**：Outlook 其它私有格式不在范围。
- **图片脱敏是 beta**：`--image-crop` 启用，OCR 定位敏感文字区域并**裁剪掉**（图片变小）。需手动安装 tesseract + 中文语言包（`pip install -e ".[image]"` + 系统 tesseract）。

## 版本历史

| 版本 | 内容 |
|------|------|
| **V5** (0.5.0) | 规则管理可视化（描述代替正则）+ 规则集新建/切换/导入导出 + 人员清单表格脱敏 + 文件列表预览/产出选择/防传错 + **上传敏感信息规定文档（PDF/Word/邮件/文本）→ AI 解析生成对应规则** |
| **V4** (0.4.0) | Windows 桌面 GUI（PyQt5，拖拽/异步/实时处理·脱敏·进度统计）+ 引擎脱敏计数 + 打包脚本 |
| **V3.1** (0.3.1) | LLM 规则生成（`rules generate`，OpenAI 兼容，专用规则生成器强约束） |
| **V3** (0.3.0) | 姓名/公司名文本识别（`--scan-names`）+ 全量人员清单（`--person-list`）+ Outlook .msg + Excel 多 sheet + 图片裁剪脱敏（beta `--image-crop`），纯本地零网络 |
| **V2** (0.2.0) | 多格式支持：Excel/JSON/邮件/PDF/Word，双引擎架构（表格按列 + 文本全文 PII 扫描） |
| **V1** (0.1.0) | CSV 脱敏 + 确定性伪名化 + 数据驱动规则 + 审计日志 |

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
pytest            # 91 个测试，覆盖确定性/边缘/性能/各格式端到端/姓名识别/LLM生成/统计计数
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
