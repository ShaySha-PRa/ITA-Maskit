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
    - 默认规则集（无显式 rules）对真实列名自动匹配（中文列名也能识别）
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

    # 默认规则集（无显式 rules）且无列匹配 → 自动匹配真实列名
    # （不同公司/文件的列名不一样，用语义关键词自动映射）
    if not effective_specs and all(s.optional for s in ruleset.specs):
        from maskit.rules.matcher import auto_match_columns

        effective_specs = auto_match_columns(cols)

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
    details: dict | None = None,
) -> int:
    """脱敏 CSV → CSV，返回处理行数。

    details（可选）：记录 masked 数（脱敏单元格数）。
    """
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    # Polars 用 utf8 而非 utf-8；映射 gbk 为 gb18030（Polars 不支持 gbk）
    pl_encoding = "utf8" if encoding in ("utf-8", "utf8") else encoding

    # 读取：全部列 cast 为字符串，避免 datetime/数字混合 schema 推断失败
    # （GUI 用户可能上传含日期/空值混合的 CSV）
    try:
        df = pl.read_csv(
            src,
            encoding=pl_encoding,
            infer_schema_length=None,  # 全量推断，避免边界列类型冲突
        )
        # 统一转成字符串列，消除 datetime/i64 等类型差异
        df = df.with_columns(
            [pl.col(c).cast(pl.Utf8) for c in df.columns]
        )
    except Exception as exc:
        raise ValueError(f"无法读取输入文件（可能为空或格式错误）: {src} ({exc})") from exc

    # 空文件检测
    if df.height == 0:
        raise ValueError(f"输入文件无数据: {src}")

    masked_df, masked_count = _mask_dataframe(df, ruleset, pepper)
    if masked_df.height == 0:
        raise ValueError(f"输入文件无数据: {src}")

    masked_df.write_csv(dst)
    if details is not None:
        details["masked"] = masked_count
        details["processed"] = masked_df.height
    return masked_df.height

