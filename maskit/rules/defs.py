"""内置规则定义（数据驱动）。

每类规则 = 识别正则 + 遮盖模板 + 伪名模板。规则定义带版本号，
YAML 可覆盖（同名）或新增（新名），实现「脱敏要求每年变化时
只改 YAML、不动代码」。

schema（rules.yaml）两段式：
  rule_defs:  规则定义（match/mask/pseudo/version）
  rules:      列映射（column/rule/strategy）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# 内置规则默认版本
DEFAULT_VERSION = "1.0"

# 内置规则定义（v1.0，YAML 可覆盖）
# match 为识别正则；mask 为遮盖模板；pseudo 为确定性伪名模板（{hash:8} 占位）。
# text_scanable=True → 该规则可用于文本流 PII 扫描（邮件/PDF/Word 正文）；
# match 太宽泛（如 .+）的规则不可全文扫描，仅列式可用。
BUILTIN_RULE_DEFS: dict[str, dict[str, Any]] = {
    "name": {
        "version": DEFAULT_VERSION,
        "match": r".+",  # 中文/英文姓名，由列语义 + 列名判断
        "mask": "{first}*",
        "pseudo": "N-{hash:8}",
        "normalize": "default",
        "text_scanable": False,  # 无法在文本流中区分名字
        "keywords": ["姓名", "名字", "name", "applicant", "员工", "人员", "签约", "nickname", "昵称"],
    },
    "email": {
        "version": DEFAULT_VERSION,
        "match": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "mask": "{first}***@{domain}",
        "pseudo": "p{hash:8}@masked.local",
        "normalize": "lower",
        "text_scanable": True,
        "keywords": ["邮箱", "邮件", "email", "mail", "e-mail", "电邮"],
    },
    "ip": {
        "version": DEFAULT_VERSION,
        "match": r"^\d{1,3}(\.\d{1,3}){3}$",
        "mask": "*.*.*.*",  # 全遮盖
        "pseudo": "IP-{hash:8}",
        "normalize": "none",
        "text_scanable": True,
        "keywords": ["ip地址", "ip", "地址"],
    },
    "phone": {
        "version": DEFAULT_VERSION,
        "match": r"^\+?\d[\d\s.\-()]{6,}$",
        "mask": "{head:3}****{tail:4}",
        "pseudo": "{digits}",  # 确定性数字，由 HMAC 派生
        "normalize": "phone",
        "text_scanable": True,
        "keywords": ["手机", "电话", "phone", "mobile", "tel", "联系", "联系电话"],
    },
    "employee_id": {
        "version": DEFAULT_VERSION,
        "match": r"^[A-Za-z0-9]+-\d{4,}$",  # EID-7F3A 风格
        "mask": "{prefix}-***",
        "pseudo": "{prefix}-{hash:8}",
        "normalize": "upper",
        "text_scanable": True,
        "keywords": ["工号", "员工编号", "员工id", "员工号", "employee_id", "编号", "工牌"],
    },
    "account": {
        "version": DEFAULT_VERSION,
        "match": r"^[A-Za-z0-9_]{3,}$",
        "mask": "{first}***{last}",
        "pseudo": "A-{hash:8}",
        "normalize": "default",
        "text_scanable": False,  # 纯字母数字无边界，易误伤普通单词
        "keywords": ["账号", "账户", "account", "username", "登录名", "login"],
    },
    "company": {
        "version": DEFAULT_VERSION,
        "match": r".+",
        "mask": "{first}*",
        "pseudo": "C-{hash:8}",
        "normalize": "default",
        "text_scanable": False,  # 无法在文本流中区分公司名
        "keywords": ["公司", "签约主体", "主体", "vendor", "company", "企业", "单位", "甲方"],
    },
    "app_version": {
        "version": DEFAULT_VERSION,
        "match": r"^[vV]?\d+(\.\d+){1,3}$",
        "mask": "v{major}.*.*",
        "pseudo": "V-{hash:8}",
        "normalize": "lower",
        "text_scanable": True,
        "keywords": ["版本", "version", "软件版本", "app_version"],
    },
    "id_card": {
        "version": DEFAULT_VERSION,
        "match": r"^\d{17}[\dXx]$",  # 18 位身份证号（末位可为 X）
        "mask": "{head:6}**********{tail:4}",  # 保留前6后4，中间10位隐藏
        "pseudo": "ID-{hash:8}",
        "normalize": "upper",
        "text_scanable": True,
        "keywords": ["身份证", "证件号", "id_card", "idcard", "idnumber", "证件号码", "身份证号"],
    },
    "bank_card": {
        "version": DEFAULT_VERSION,
        "match": r"^\d{16,19}$",  # 银行卡号 16-19 位纯数字
        "mask": "{head:6}**********{tail:4}",  # 保留前6后4，中间隐藏
        "pseudo": "BC-{hash:8}",
        "normalize": "none",
        "text_scanable": True,
        "keywords": ["银行卡", "卡号", "银行账户", "bank_card", "bankcard", "bank_account", "银行卡号"],
    },
    # 合规敏感，默认关闭（需在 YAML 显式启用）
    "ssn": {
        "version": DEFAULT_VERSION,
        "match": r"^\d{3}-\d{2}-\d{4}$",
        "mask": "***-**-{tail:4}",
        "pseudo": "SSN-{hash:8}",
        "normalize": "none",
        "default_disabled": True,
        "text_scanable": True,
    },
    "credit_card": {
        "version": DEFAULT_VERSION,
        "match": r"^\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}$",
        "mask": "****-****-****-{tail:4}",
        "pseudo": "CC-{hash:8}",
        "normalize": "none",
        "default_disabled": True,
        "text_scanable": True,
    },
}

# 规范化函数注册表（rule_defs.normalize 引用）
from maskit.normalize import (
    normalize_default,
    normalize_hyphen,
    normalize_lower,
    normalize_trim,
)


def _phone_normalize(value: str) -> str:
    """电话专有规范化：保留数字与可选 + 号（去掉分隔符/空格/括号）。"""
    v = normalize_trim(value)
    return re.sub(r"[\s.\-–—()]+", "", v)


def _upper_preserve_hyphen(value: str) -> str:
    """保留连字符的大写归一（用于 EID-7F3A 这类带前缀的 ID）。"""
    return value.strip().upper()


NORMALIZERS: dict[str, Any] = {
    "default": normalize_default,
    "lower": normalize_lower,
    "trim": normalize_trim,
    "hyphen": normalize_hyphen,
    "none": lambda v: v.strip(),
    "phone": _phone_normalize,
    "upper": _upper_preserve_hyphen,
}


@dataclass
class RuleDef:
    """单条规则定义（已解析）。"""

    name: str
    version: str
    match: str
    mask: str
    pseudo: str
    normalize: str = "default"
    default_disabled: bool = False
    text_scanable: bool = False  # 是否可用于文本流 PII 扫描
    keywords: list[str] = field(default_factory=list)  # 列名自动匹配语义关键词

    @property
    def regex(self) -> re.Pattern:
        return re.compile(self.match)


@dataclass
class RuleSpec:
    """列映射：某一列用哪个规则、哪个策略。"""

    column: str
    rule: str
    strategy: str  # "mask" | "pseudo"
    optional: bool = False  # True → 列不存在时静默跳过（默认规则集用）；False → 硬错误

    def validate(self, available: set[str]) -> None:
        """校验策略合法、规则存在。"""
        if self.strategy not in ("mask", "pseudo"):
            raise ValueError(
                f"列 {self.column!r} 的策略 {self.strategy!r} 非法（应为 mask 或 pseudo）"
            )
        if self.rule not in available:
            raise ValueError(f"列 {self.column!r} 引用了不存在的规则 {self.rule!r}")


@dataclass
class RuleSet:
    """解析后的完整规则集（规则定义 + 列映射）。"""

    defs: dict[str, RuleDef] = field(default_factory=dict)
    specs: list[RuleSpec] = field(default_factory=list)

    @property
    def version(self) -> str:
        """规则集版本 = 所有规则版本的拼接哈希，用于审计追溯。"""
        import hashlib

        raw = "|".join(
            f"{d.name}:{d.version}" for d in sorted(self.defs.values(), key=lambda d: d.name)
        )
        return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def strategy_for(self, column: str) -> str | None:
        """返回某列的策略（mask/pseudo），未映射返回 None。"""
        for s in self.specs:
            if s.column == column:
                return s.strategy
        return None
