"""Shared regexes for structured cell scan and document scan."""

from __future__ import annotations

import re

# 值级/格内只扫强特征；phone/app_version 误伤日期小数。
VALUE_SCAN_RULES = frozenset({"email", "ip", "id_card", "bank_card"})

_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)"
CELL_IP_RE = re.compile(
    rf"(?<![vV0-9A-Za-z.]){_OCTET}(?:\.{_OCTET}){{3}}(?![0-9A-Za-z])(?!\.\d)"
)
DATE_LIKE_VERSION_RE = re.compile(r"^(19|20)\d{2}[./-]\d{1,2}([./-]\d{1,2})?$")
DEPT_LIKE_RE = re.compile(r"^[\u4e00-\u9fff]{1,8}(部|处|科|组|室)$")
SPACED_ID_RE = re.compile(r"\d{6}\s+\d{8}\s+\d{3}[\dXx]")
DASHED_BANK_RE = re.compile(r"\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}(?:[\s\-]\d{1,3})?")
EMAIL_BODY_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CATCHALL_BODIES = frozenset({".+", ".*", ".+?", ".*?"})

# 文档路径专用：中国大陆手机（11 位 1[3-9]），允许 3-4-4 分隔。
# 不用规则里过宽的 \d[\d\s.\-()]+，避免日期/空格身份证被当成电话。
DOC_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?86[\s\-.]?)?1[3-9](?:\d{9}|\d[\s\-.]?\d{4}[\s\-.]?\d{4})(?!\d)"
)


def strip_anchors(pattern: str) -> str:
    """去掉 ^ 和 $，供格内/全文扫描。"""
    return pattern.removeprefix("^").removesuffix("$")
