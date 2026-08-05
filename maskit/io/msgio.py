"""Outlook 邮件 (.msg) 读取。

extract_msg 读取 .msg → asEmailMessage() 转成标准 email.message →
复用 emailio.mask_email_message 脱敏 → 输出 .eml。

技术说明：Python 生态无库能可靠回写 .msg（OLE 复合文档私有格式），
因此 .msg 输入脱敏后输出标准 .eml（可打开/转发/作证据）。
"""
from __future__ import annotations

from pathlib import Path

from maskit.io.emailio import mask_email_message
from maskit.rules.defs import RuleSet

try:
    from extract_msg import Message as MsgMessage
except ImportError:  # pragma: no cover
    MsgMessage = None


def mask_msg_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    strategy: str = "mask",
) -> int:
    """脱敏 .msg → .eml，返回 1（单封邮件）。"""
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    if MsgMessage is None:
        raise ValueError("需要安装 extract_msg 才能处理 .msg")

    try:
        with MsgMessage(str(src)) as msg:
            eml = msg.asEmailMessage()
    except Exception as exc:
        raise ValueError(f"无法读取 Outlook 邮件: {src} ({exc})") from exc

    if eml is None:
        raise ValueError(f"Outlook 邮件无内容: {src}")

    mask_email_message(eml, ruleset, pepper, strategy)

    from email import policy

    dst.write_bytes(eml.as_bytes(policy=policy.default))
    return 1
