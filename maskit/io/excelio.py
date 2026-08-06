"""Excel 读写。

openpyxl 读取全部 sheet，逐 sheet 脱敏后写回，保留多 sheet 结构。
每 sheet 独立按列脱敏（_mask_dataframe）。
"""
from __future__ import annotations

from pathlib import Path

from maskit.io.csvio import _mask_dataframe
from maskit.rules.defs import RuleSet

# openpyxl 用于读/写 xlsx（保留多 sheet）
try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    load_workbook = None


def mask_excel_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
) -> int:
    """脱敏 Excel（全部 sheet）→ Excel，返回总处理行数。

    用 openpyxl 读取全部 sheet → 逐 sheet 转 Polars 脱敏 → 写回。
    """
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    if load_workbook is None:
        raise ValueError("需要安装 openpyxl 才能处理 Excel")

    try:
        wb = load_workbook(src, data_only=True)
    except Exception as exc:
        raise ValueError(f"无法读取 Excel 文件: {src} ({exc})") from exc

    if not wb.sheetnames:
        raise ValueError(f"Excel 文件无工作表: {src}")

    import polars as pl

    total = 0
    for ws in wb.worksheets:
        # 读取 sheet 数据为 list[list]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(rows[0])]
        data = rows[1:]
        if not data:
            continue
        df = pl.DataFrame(data, schema=header, orient="row")
        # 统一转成字符串列：避免 date/datetime 列（datetime[μs]）在脱敏/写回时
        # 与字符串列类型冲突（真实 Excel 常有日期列）
        df = df.with_columns([pl.col(c).cast(pl.Utf8) for c in df.columns])
        masked, _ = _mask_dataframe(df, ruleset, pepper)
        total += masked.height
        # 写回该 sheet
        _write_sheet(ws, header, masked)

    wb.save(dst)
    return total


def _write_sheet(ws, header: list[str], df) -> None:
    """把脱敏后的 DataFrame 写回 openpyxl worksheet。"""
    # 先清空原内容
    ws.delete_rows(1, ws.max_row)
    # 写 header
    ws.append(header)
    # 写数据（DataFrame 已全为字符串列）
    for row in df.iter_rows():
        ws.append(list(row))
