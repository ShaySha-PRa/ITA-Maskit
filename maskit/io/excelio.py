"""Excel 读写。

用 Polars read_excel（openpyxl 引擎）读取，_mask_dataframe 脱敏，write_excel 写出。
v2 只处理第一个 sheet（审计常见场景）。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from maskit.io.csvio import _mask_dataframe
from maskit.rules.defs import RuleSet


def mask_excel_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
) -> int:
    """脱敏 Excel（第一个 sheet）→ Excel，返回处理行数。"""
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    # 读取第一个 sheet（read_excel 返回 {sheet_name: DataFrame}）
    try:
        sheets = pl.read_excel(src, engine="openpyxl")
        if isinstance(sheets, dict):
            if not sheets:
                raise ValueError(f"Excel 文件无工作表: {src}")
            df = next(iter(sheets.values()))
        else:
            df = sheets
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"无法读取 Excel 文件: {src} ({exc})") from exc

    if df.height == 0:
        raise ValueError(f"Excel 文件无数据: {src}")

    masked = _mask_dataframe(df, ruleset, pepper)
    if masked.height == 0:
        raise ValueError(f"Excel 文件无数据: {src}")

    masked.write_excel(dst)
    return masked.height
