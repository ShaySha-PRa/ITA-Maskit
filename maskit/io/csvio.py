"""数据后端：Polars 表格类格式读写。

CSV/Excel/JSON 共用同一个 `_mask_dataframe`（按列脱敏），
各自 reader/writer 不同。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from maskit.rules.defs import RuleSet


def _mask_dataframe(df: pl.DataFrame, ruleset: RuleSet, pepper: str | None) -> pl.DataFrame:
    """对 DataFrame 按规则集脱敏（CSV/Excel/JSON 共用）。

    - 映射列按规则/策略处理，未映射列原样透传
    - 规则引用缺列：显式 YAML → 硬错误；默认规则集（optional）→ 跳过
    - null 保持 null
    """
    cols = df.columns
    effective_specs = []
    for spec in ruleset.specs:
        if spec.column not in cols:
            if spec.optional:
                continue  # 默认规则集：缺列跳过
            raise ValueError(f"规则引用了不存在的列: {spec.column!r}")
        effective_specs.append(spec)

    out = df.select(
        [_apply_column_expr(pl.col(c), c, effective_specs, ruleset, pepper) for c in cols]
    )
    return out


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

    df = _mask_dataframe(lf.collect(), ruleset, pepper)
    if df.height == 0:
        raise ValueError(f"输入文件无数据: {src}")

    df.write_csv(dst)
    return df.height


def _apply_column_expr(
    col: pl.Expr,
    column: str,
    effective_specs: list,
    ruleset: RuleSet,
    pepper: str | None,
) -> pl.Expr:
    """为某一列构造脱敏表达式。未映射列 → 原样透传。"""
    spec = next((s for s in effective_specs if s.column == column), None)
    if spec is None:
        return col  # 透传

    rule = ruleset.defs.get(spec.rule)
    if rule is None:
        raise ValueError(f"规则 {spec.rule!r} 未定义")
    if rule.default_disabled:
        raise ValueError(f"规则 {spec.rule!r} 默认关闭，请在 YAML 中显式启用")

    # 用 map_elements 应用单值处理函数（engine 内部处理 mask/pseudo 分支）
    from maskit.rules.engine import _apply_single

    # B023：用默认参数绑定循环变量，避免闭包捕获引用
    return (
        col.cast(pl.Utf8)
        .map_elements(
            lambda v, r=rule, s=spec: _apply_single(
                r, v if v is not None else "", s.strategy, pepper
            ),
            return_dtype=pl.Utf8,
        )
    )
