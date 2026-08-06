"""JSON / JSONL 读写。

Polars read_json / read_ndjson 读取，_mask_dataframe 脱敏，write_ndjson 写出。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from maskit.io.csvio import _mask_dataframe
from maskit.rules.defs import RuleSet


def mask_json_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
) -> int:
    """脱敏 JSON / JSONL → JSONL，返回处理行数。"""
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    ext = src.suffix.lower()
    try:
        if ext in {".jsonl", ".ndjson"}:
            df = pl.read_ndjson(src)
        elif ext == ".json":
            # 数组对象 → read_json；否则尝试 JSONL 兼容
            try:
                df = pl.read_json(src)
            except Exception:  # noqa: BLE001 — 数组 JSON 解析失败回退 JSONL
                df = pl.read_ndjson(src)
        else:
            raise ValueError(f"不支持的 JSON 扩展名: {ext}")
    except Exception as exc:
        raise ValueError(f"无法读取 JSON 文件: {src} ({exc})") from exc

    if df.height == 0:
        raise ValueError(f"JSON 文件无数据: {src}")

    masked, _ = _mask_dataframe(df, ruleset, pepper)
    if masked.height == 0:
        raise ValueError(f"JSON 文件无数据: {src}")

    masked.write_ndjson(dst)
    return masked.height
