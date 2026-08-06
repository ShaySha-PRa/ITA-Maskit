"""数据后端：Polars 表格类格式读写。

CSV/Excel/JSON 共用同一个 `_mask_dataframe`（按列脱敏），
各自 reader/writer 不同。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from maskit.rules.defs import RuleSet


def _mask_dataframe(
    df: pl.DataFrame, ruleset: RuleSet, pepper: str | None
) -> tuple[pl.DataFrame, int]:
    """对 DataFrame 按规则集脱敏，返回 (脱敏后 DataFrame, 脱敏单元格数)。

    - 映射列按规则/策略处理，未映射列原样透传
    - 规则引用缺列：显式 YAML → 硬错误；默认规则集（optional）→ 跳过
    - null 保持 null
    """
    from maskit.rules.engine import apply_rules

    cols = df.columns
    effective_specs = []
    for spec in ruleset.specs:
        if spec.column not in cols:
            if spec.optional:
                continue  # 默认规则集：缺列跳过
            raise ValueError(f"规则引用了不存在的列: {spec.column!r}")
        effective_specs.append(spec)

    # 用临时规则集（仅有效列）调用 apply_rules 获取计数
    from maskit.rules.defs import RuleSet

    effective_ruleset = RuleSet(defs=ruleset.defs, specs=effective_specs)
    masked_df, masked_count = apply_rules(df, effective_ruleset, pepper)
    return masked_df, masked_count


def mask_csv_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    encoding: str = "utf-8",
) -> int:
    """脱敏 CSV → CSV，返回处理行数。"""
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    # Polars 用 utf8 而非 utf-8；映射 gbk 为 gb18030（Polars 不支持 gbk）
    pl_encoding = "utf8" if encoding in ("utf-8", "utf8") else encoding

    lf = pl.scan_csv(src, encoding=pl_encoding)

    # 空文件检测
    try:
        first = lf.head(1).collect()
    except Exception as exc:
        raise ValueError(f"无法读取输入文件（可能为空或格式错误）: {src}") from exc
    if first.height == 0:
        raise ValueError(f"输入文件无数据: {src}")

    df, _ = _mask_dataframe(lf.collect(), ruleset, pepper)
    if df.height == 0:
        raise ValueError(f"输入文件无数据: {src}")

    df.write_csv(dst)
    return df.height

