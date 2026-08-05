"""邮件 (.eml) 读写。

stdlib email 解析 headers + body：
- headers 中 From/To/Cc/Reply-To 是邮箱地址 → 按 email 规则脱敏
- Subject 可能是姓名/公司 → 走文本扫描（有精确正则的规则）
- body（text/plain 或 text/html）→ mask_text_pii 全文扫描
重建 .eml 保持结构。
"""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path

from maskit.rules.defs import RuleSet
from maskit.rules.engine import _apply_single
from maskit.text import mask_text_pii

# 含邮箱地址的 header（按 email 规则脱敏）
_EMAIL_HEADERS = {"from", "to", "cc", "reply-to", "bcc"}
# 主题：走文本扫描
_SUBJECT_HEADERS = {"subject"}


def _mask_email_address(addr: str, ruleset: RuleSet, pepper: str | None, strategy: str) -> str:
    """脱敏 header 里的邮箱地址（保留显示名，仅替换地址）。"""
    # 简单处理：若形如 "Name <addr>"，保留 Name 替换 addr；纯 addr 直接替换
    rule = ruleset.defs.get("email")
    if rule is None:
        return addr
    import re

    m = re.match(r"^(.*?)\s*<([^>]+)>$", addr)
    if m:
        name, email_addr = m.group(1), m.group(2)
        masked_addr = _apply_single(rule, email_addr, strategy, pepper)
        return f"{name} <{masked_addr}>"
    return _apply_single(rule, addr, strategy, pepper)


def _mask_header_value(
    name: str, value: str, ruleset: RuleSet, pepper: str | None, strategy: str
) -> str:
    """按 header 类型脱敏。"""
    lower = name.lower()
    if lower in _EMAIL_HEADERS:
        # 多个地址逗号分隔
        parts = [p.strip() for p in value.split(",")]
        return ", ".join(_mask_email_address(p, ruleset, pepper, strategy) for p in parts if p)
    if lower in _SUBJECT_HEADERS:
        return mask_text_pii(value, ruleset, pepper, strategy)
    return value  # 其它 header（Date/Message-ID 等）不动


def mask_email_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
) -> int:
    """脱敏 .eml → .eml，返回 1（单封邮件）。

    headers + body 均脱敏，保持邮件结构。
    """
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    try:
        raw = src.read_bytes()
        msg = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:
        raise ValueError(f"无法解析邮件文件: {src} ({exc})") from exc

    if msg is None:
        raise ValueError(f"邮件文件无内容: {src}")

    # 脱敏 headers
    for name in list(msg.keys()):
        values = msg.get_all(name)
        if values:
            masked_values = [_mask_header_value(name, v, ruleset, pepper, strategy) for v in values]
            del msg[name]
            for v in masked_values:
                msg[name] = v

    # 脱敏 body（逐 part）
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype in ("text/plain", "text/html"):
            try:
                body = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                text = body.decode(charset, errors="replace")
            except Exception:  # noqa: BLE001, S112 — 单 part 解码失败跳过，不影响整封邮件
                continue
            masked = mask_text_pii(text, ruleset, pepper, strategy)
            if masked != text:
                part.set_payload(masked, charset=charset)

    dst.write_bytes(msg.as_bytes(policy=policy.default))
    return 1
