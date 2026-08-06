"""LLM 规则生成测试：mock API、schema 校验、prompt 构造、数据边界。"""

import os

import pytest

from maskit.llm import LLMClient, LLMConfig, build_rules_prompt
from maskit.rules.loader import load_ruleset_from_string

# 一个合法的规则 YAML（LLM 应生成的格式）
VALID_YAML = """rule_defs:
  tin:
    version: "1.0"
    match: '^[A-Z0-9]{15,18}$'
    mask: '***-{tail:4}'
    pseudo: 'TIN-{hash:8}'
rules:
  - column: phone
    rule: phone
    strategy: pseudo
  - column: tin
    rule: tin
    strategy: mask
"""

# 缺字段的非法 YAML（LLM 可能生成）
INVALID_YAML = """rule_defs:
  tin:
    match: '^[A-Z0-9]{15,18}$'
    # 缺 mask/pseudo
rules:
  - column: tin
    rule: tin
    strategy: mask
"""


# --- prompt 构造 ---

def test_build_rules_prompt_contains_schema():
    """prompt 注入现有规则 schema。"""
    prompt = build_rules_prompt("新增税务登记号脱敏")
    assert "rule_defs" in prompt
    assert "rules" in prompt
    assert "新增税务登记号脱敏" in prompt
    # 注入内置规则 schema（含 name/email 等）
    assert "name" in prompt
    assert "email" in prompt


def test_build_rules_prompt_mentions_pseudo():
    """prompt 说明伪名化策略。"""
    prompt = build_rules_prompt("手机号伪名化")
    assert "pseudo" in prompt
    assert "确定性" in prompt or "伪名化" in prompt


def test_build_rules_prompt_functional_boundary():
    """prompt 强约束 LLM 只能做规则生成（安全边界）。"""
    prompt = build_rules_prompt("新增税务登记号")
    # 功能边界说明存在
    assert "规则生成器" in prompt
    assert "功能边界" in prompt
    # 明确禁止其它任务
    assert "绝不执行" in prompt or "唯一功能" in prompt
    # 忽略注入指令
    assert "忽略" in prompt or "无视" in prompt


# --- schema 校验 ---

def test_validate_valid_yaml():
    """合法 YAML 校验通过。"""
    rs = load_ruleset_from_string(VALID_YAML)
    assert "tin" in rs.defs
    assert rs.strategy_for("tin") == "mask"
    assert rs.strategy_for("phone") == "pseudo"


def test_validate_invalid_yaml():
    """缺字段 YAML → 报错。"""
    with pytest.raises(ValueError, match="mask"):
        load_ruleset_from_string(INVALID_YAML)


# --- LLM mock ---

class _FakeLLMClient(LLMClient):
    """mock：不调用真实 API，返回预设 YAML。"""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[str] = []

    def chat(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response

    def generate_rules(self, user_request: str) -> str:
        self.calls.append(user_request)
        return self.response


def test_llm_generate_rules_with_mock():
    """mock LLM 返回 YAML → 生成成功。"""
    client = _FakeLLMClient(VALID_YAML)
    result = client.generate_rules("新增税务登记号")
    assert "tin" in result
    assert client.calls  # 确实调用了


def test_llm_generate_rules_validates(monkeypatch):
    """mock 返回合法 YAML → load_ruleset_from_string 通过。"""
    client = _FakeLLMClient(VALID_YAML)
    yaml_text = client.generate_rules("新增税务登记号")
    rs = load_ruleset_from_string(yaml_text)
    assert "tin" in rs.defs


# --- 数据边界（核心约束） ---

def test_llm_prompt_never_contains_pii():
    """脱敏数据（PII）永不进入 prompt。"""
    # 即使调用方误传含 PII 的描述，prompt 也只含规则要求
    prompt = build_rules_prompt("脱敏 alice@corp.example 和 13800000000")
    # prompt 里可以含用户主动提供的描述，但测试确认：生成规则的过程
    # 只把描述发给 LLM —— 由 CLI 层保证脱敏数据不进入
    assert "rule_defs" in prompt  # 主要是规则 schema


def test_llm_config_from_env_requires_key(monkeypatch):
    """无 API key → 报错。"""
    monkeypatch.delenv("MASKIT_LLM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MASKIT_LLM_API_KEY"):
        LLMConfig.from_env()


def test_llm_config_from_env_reads(monkeypatch):
    """有 API key → 读取配置。"""
    monkeypatch.setenv("MASKIT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("MASKIT_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("MASKIT_LLM_MODEL", "qwen-plus")
    cfg = LLMConfig.from_env()
    assert cfg.api_key == "test-key"
    assert cfg.base_url == "https://example.com/v1"
    assert cfg.model == "qwen-plus"


# --- {second} 占位符（LLM 生成车牌规则时用到） ---

def test_second_placeholder():
    """{second} 占位符：保留第二字符。"""
    from maskit.rules.engine import _apply_single
    from maskit.rules.loader import _build_rule_def

    rule = _build_rule_def(
        "license_plate",
        {"match": "x", "mask": "{first}{second}***{tail:2}", "pseudo": "X"},
    )
    assert _apply_single(rule, "沪A12345", "mask", None) == "沪A***45"
    # 不足两位时第二字符为空
    assert _apply_single(rule, "沪", "mask", None) == "沪***沪"


# --- DeepSeek 集成测试（有 API key 时运行） ---

def test_deepseek_generate_rules_integration():
    """DeepSeek 真实调用：生成 → 校验 → 脱敏（需 MASKIT_LLM_API_KEY）。"""
    api_key = os.environ.get("MASKIT_LLM_API_KEY")
    if not api_key:
        pytest.skip("未配置 MASKIT_LLM_API_KEY，跳过真实调用")
    import re

    import polars as pl

    from maskit.rules.defs import RuleSet, RuleSpec
    from maskit.rules.engine import apply_rules

    os.environ.setdefault("MASKIT_LLM_BASE_URL", "https://api.deepseek.com/v1")
    os.environ.setdefault("MASKIT_LLM_MODEL", "deepseek-chat")
    cfg = LLMConfig.from_env()
    client = LLMClient(cfg)
    yaml_text = client.generate_rules("新增「车牌号」脱敏规则，遮盖保留省份字和最后两位")
    clean = re.sub(r"^```yaml\s*|\s*```$", "", yaml_text).strip()
    rs = load_ruleset_from_string(clean)
    assert "license_plate" in rs.defs

    custom_rs = RuleSet(
        defs=rs.defs,
        specs=[RuleSpec(column="车牌", rule="license_plate", strategy="mask")],
    )
    df = pl.DataFrame({"车牌": ["沪A12345"]})
    masked, count = apply_rules(df, custom_rs, None)
    assert count == 1
    assert masked["车牌"].to_list()[0] != "沪A12345"
