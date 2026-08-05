"""共享 Normalizer 层。

规则在「规范化后」的值上做 HMAC 确定性伪名化，这样跨表/跨批次
「138-0000-0000」与「13800000000」能映射到同一伪名（保留关联性）。

设计：通用归一（trim/大小写/连字符）抽成工具函数；专有规范化
（如 phone 去国家码）由每个规则的可选扩展实现。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


def normalize_trim(value: str) -> str:
    """去除首尾空白。"""
    return value.strip()


def normalize_lower(value: str) -> str:
    """ASCII 小写归一（中文无大小写，不受影响）。"""
    return value.casefold()


def normalize_hyphen(value: str) -> str:
    """连字符/空格/点号归一：`138-0000-0000`、`138 0000 0000`、`138.0000.0000`
    全部折叠成 `13800000000`。"""
    return re.sub(r"[\s.\-–—]+", "", value)


def normalize_default(value: str) -> str:
    """默认规范化：trim → 小写 → 去连字符。"""
    return normalize_hyphen(normalize_lower(normalize_trim(value)))


@dataclass(frozen=True)
class NormalizedValue:
    """规范化结果：保留归一后的值与是否发生归一（供调试/审计）。"""

    value: str
    changed: bool


def normalize_with_trace(value: str, norm_fn) -> NormalizedValue:
    """执行指定规范化函数，返回归一值与是否变化。"""
    out = norm_fn(value)
    return NormalizedValue(value=out, changed=out != value)
