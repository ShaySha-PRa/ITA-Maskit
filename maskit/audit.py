"""审计日志（JSONL）。

每次脱敏运行记录：时间戳、输入文件、规则集版本、pepper 指纹
（不存明文，domain separation）、处理行数、输出文件。

路径：~/.maskit/audit.log（可用 MASKIT_AUDIT_LOG 覆盖）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from maskit.rules.engine import audit_key, hmac_digest


def audit_log_path() -> Path:
    """审计日志文件路径。"""
    override = os.environ.get("MASKIT_AUDIT_LOG")
    if override:
        return Path(override)
    return Path.home() / ".maskit" / "audit.log"


def pepper_fingerprint(pepper: str) -> str:
    """pepper 指纹：对 pepper 用审计专用 key 再 HMAC，不存明文。"""
    return "fp:" + hmac_digest(pepper, audit_key(pepper), 12)


def log_run(
    *,
    input_file: str,
    output_file: str,
    ruleset_version: str,
    pepper: str | None,
    rows: int,
    mask_columns: list[str],
    pseudo_columns: list[str],
) -> None:
    """写一条审计日志。pepper 为空则不记录指纹（全 mask 运行）。"""
    path = audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "input_file": input_file,
        "output_file": output_file,
        "ruleset_version": ruleset_version,
        "rows": rows,
        "mask_columns": mask_columns,
        "pseudo_columns": pseudo_columns,
        "pepper_fingerprint": pepper_fingerprint(pepper) if pepper else None,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_logs(limit: int = 50) -> list[dict]:
    """读取最近 N 条审计日志（供 `maskit audit`）。"""
    path = audit_log_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries
