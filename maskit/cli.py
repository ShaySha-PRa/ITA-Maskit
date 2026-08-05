"""CLI 入口（Typer）。

命令：
  maskit mask <input.csv> [--rules rules.yaml] [--pepper SECRET] [-o out.csv]
  maskit demo [--rows N] [--seed N]
  maskit rules list
  maskit audit [--limit N]

分层退出码：
  用户错误（缺 pepper/缺列/非法 YAML）→ 2，一行清晰中文错误，无 traceback
  运行失败（I/O/编码）            → 1，保留 traceback
  成功                            → 0
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

from maskit import __version__
from maskit.audit import log_run, read_logs
from maskit.demo import write_demo
from maskit.rules.loader import list_rules, load_ruleset

app = typer.Typer(help="ITA-maskit — 高性能数据脱敏工具", no_args_is_help=True)
rules_app = typer.Typer(help="规则相关命令")
app.add_typer(rules_app, name="rules")


class UserError(Exception):
    """用户错误（退出码 2）：缺 pepper、缺列、非法 YAML 等。"""


def _resolve_pepper(cli_pepper: str | None) -> str | None:
    """pepper 来源：CLI 参数 > 环境变量。pseudo 激活时缺 pepper 报错在引擎层。"""
    if cli_pepper:
        return cli_pepper
    return os.environ.get("MASKIT_PEPPER")


@app.command()
def mask(
    input_path: str = typer.Argument(..., help="输入文件路径（csv/xlsx/json/eml/pdf/docx）"),
    rules_file: str | None = typer.Option(
        None, "--rules", "-r", help="规则 YAML 文件（缺省用内置默认规则集）"
    ),
    pepper: str | None = typer.Option(
        None, "--pepper", help="伪名化密钥（也可用 MASKIT_PEPPER 环境变量）"
    ),
    encoding: str = typer.Option("utf-8", "--encoding", help="输入编码（表格格式，utf-8/gbk）"),
    strategy: str = typer.Option(
        "mask", "--strategy", help="文本格式（邮件/PDF/Word）的扫描策略：mask 或 pseudo"
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="输出路径（缺省为 input.masked.<ext>）"
    ),
) -> None:
    """对文件执行脱敏（支持 csv/xlsx/json/eml/pdf/docx）。"""
    try:
        ruleset = load_ruleset(rules_file)
        resolved_pepper = _resolve_pepper(pepper)

        from maskit.io import is_text_format

        is_text = is_text_format(input_path)
        # 文本格式：全文扫描，用 --strategy；表格格式：按列，规则集决定策略
        if is_text:
            has_pseudo = strategy == "pseudo"
        else:
            has_pseudo = any(s.strategy == "pseudo" for s in ruleset.specs)
        if has_pseudo and not resolved_pepper:
            raise UserError(
                "检测到 pseudo（确定性伪名化）策略但未提供 --pepper（或 MASKIT_PEPPER 环境变量）。"
                "伪名化需要密钥才能保证确定性，请提供 pepper 后重试。"
            )

        in_path = Path(input_path)
        out = output or str(in_path.with_suffix(".masked" + in_path.suffix))
        from maskit.io import mask_file

        rows = mask_file(input_path, out, ruleset, resolved_pepper, encoding, strategy)

        # 审计日志
        if is_text:
            mask_cols, pseudo_cols = [], [input_path] if strategy == "pseudo" else []
        else:
            mask_cols = [s.column for s in ruleset.specs if s.strategy == "mask"]
            pseudo_cols = [s.column for s in ruleset.specs if s.strategy == "pseudo"]
        log_run(
            input_file=input_path,
            output_file=out,
            ruleset_version=ruleset.version,
            pepper=resolved_pepper,
            rows=rows,
            mask_columns=mask_cols,
            pseudo_columns=pseudo_cols,
        )

        typer.echo(f"✓ 已脱敏 {rows} 项 → {out}")
        if pseudo_cols:
            typer.echo(f"  伪名化: {', '.join(pseudo_cols)}（确定性，跨文件可关联）")
        if mask_cols:
            typer.echo(f"  遮盖列: {', '.join(mask_cols)}")
        typer.echo(f"  规则集版本: {ruleset.version}")
    except UserError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)
    except ValueError as exc:
        # YAML 解析错误、缺列、规则非法等用户错误
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)
    except Exception as exc:
        # 运行失败：保留 traceback，退出码 1
        raise typer.Exit(code=1) from exc


@app.command()
def demo(
    rows: int = typer.Option(100_000, "--rows", help="演示数据行数"),
    seed: int = typer.Option(42, "--seed", help="随机种子（确定性）"),
    output: str = typer.Option(
        "demo_data.csv", "--output", "-o", help="演示数据输出路径"
    ),
) -> None:
    """生成确定性演示数据（含各类敏感字段）。"""
    path = write_demo(output, rows=rows, seed=seed)
    typer.echo(f"✓ 已生成演示数据 {rows} 行 → {path}")
    typer.echo(f"  示例运行: maskit mask {path} --rules demo-rules.yaml --pepper <密钥>")
    typer.echo("  演示 pepper 可写入 .maskit-demo.env 后 source 使用")


@rules_app.command("list")
def rules_list() -> None:
    """列出可用规则。"""
    for r in list_rules():
        tag = " (默认关闭)" if r["default_disabled"] else ""
        typer.echo(f"  {r['rule']:<14} v{r['version']:<5} mask={r['mask']!r:<20} pseudo={r['pseudo']!r}{tag}")


@app.command()
def audit(
    limit: int = typer.Option(50, "--limit", help="显示最近 N 条"),
) -> None:
    """查看审计日志。"""
    entries = read_logs(limit=limit)
    if not entries:
        typer.echo("（无审计记录）")
        return
    for e in entries:
        cols = []
        if e.get("mask_columns"):
            cols.append(f"mask:{','.join(e['mask_columns'])}")
        if e.get("pseudo_columns"):
            cols.append(f"pseudo:{','.join(e['pseudo_columns'])}")
        fp = e.get("pepper_fingerprint") or "无"
        typer.echo(
            f"  {e.get('ts','?')[:19]}  {e.get('input_file','?'):<24} "
            f"rows={e.get('rows','?')}  rules={e.get('ruleset_version','?')}  "
            f"[{','.join(cols)}]  pepper={fp}"
        )


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ITA-maskit {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", help="显示版本", callback=_version_callback
    ),
) -> None:
    """ITA-maskit CLI。"""


def entry() -> None:
    """console_scripts 入口（无参数时显示帮助并退出 0）。"""
    if len(sys.argv) == 1:
        typer.echo("ITA-maskit — 高性能数据脱敏工具。运行 `maskit --help` 查看用法。")
        raise SystemExit(0)
    app()


if __name__ == "__main__":
    entry()
