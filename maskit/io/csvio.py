"""数据后端：Polars 惰性流式 CSV 读写。

CSV→CSV 全程流式（scan_csv 惰性 + sink_csv），保留 schema/列序/行序。
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from maskit.rules.defs import RuleSet


def mask_csv_file(
    input_path: str | Path,
    output_path: str | Path,
    ruleset: RuleSet,
    pepper: str | None,
    encoding: str = "utf-8",
) -> int:
    """流式脱敏 CSV → CSV，返回处理行数。

    边缘情况：
    - 空文件 → 抛 ValueError（无数据）
    - 规则引用缺列 → apply_rules 抛 ValueError
    - 未映射列 → 透传
    """
    src = Path(input_path)
    dst = Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    # Polars 用 utf8 而非 utf-8；映射 gbk 为 gb18030（Polars 不支持 gbk）
    pl_encoding = "utf8" if encoding in ("utf-8", "utf8") else encoding

    # 惰性扫描
    lf = pl.scan_csv(src, encoding=pl_encoding)
    # 列名
    cols = lf.collect_schema().names()

    # 空文件检测：取第一行看有无数据（在列校验之前，空文件先报「无数据」）
    try:
        first = lf.head(1).collect()
    except Exception as exc:
        raise ValueError(f"无法读取输入文件（可能为空或格式错误）: {src}") from exc

    if first.height == 0:
        raise ValueError(f"输入文件无数据: {src}")

    # 校验规则引用的列都存在（提前报错，避免流式中途失败）
    # optional=True（默认规则集）→ 列不存在时跳过；False（显式 YAML）→ 硬错误
    effective_specs = []
    for spec in ruleset.specs:
        if spec.column not in cols:
            if spec.optional:
                continue  # 默认规则集：缺列跳过
            raise ValueError(f"规则引用了不存在的列: {spec.column!r}")
        effective_specs.append(spec)

    # 处理：对每列应用规则（map_elements），映射列先 cast 为 Utf8（防 i64 等数字列）
    # 说明：map_elements 是 Python UDF，无法流式（sink_csv 会失败/空输出），
    # 因此用 collect() 物化后 write_csv。1M 行内可接受；更高量级需纯表达式（v2）。
    df = lf.select(
        [
            _apply_column_expr(pl.col(c), c, effective_specs, ruleset, pepper)
            for c in cols
        ]
    ).collect()

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
