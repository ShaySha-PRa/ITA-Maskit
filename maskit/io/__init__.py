"""数据读写子包 + 统一入口。

`mask_file` 按扩展名分发到表格引擎（CSV/Excel/JSON）或文本引擎（邮件/PDF/Word）。
"""
from __future__ import annotations

from pathlib import Path

from maskit.rules.defs import RuleSet


def _ext(path) -> str:
    return Path(path).suffix.lower()


# 文本格式：无「列」，全文 PII 扫描（.msg 输出 .eml，其余同格式）
_TEXT_FORMATS = {".eml", ".msg", ".pdf", ".docx"}


def mask_file(
    input_path,
    output_path,
    ruleset: RuleSet,
    pepper: str | None,
    encoding: str = "utf-8",
    strategy: str = "mask",
    scan_names: bool = False,
    person_list: set[str] | None = None,
) -> int:
    """统一脱敏入口：按扩展名分发，返回处理行数/页数/段数。

    表格格式（CSV/Excel/JSON）：按列脱敏，strategy 由 ruleset 每列决定。
    文本格式（邮件/PDF/Word）：全文 PII 扫描，strategy 参数指定，
    scan_names=True 时额外识别姓名/公司名（纯本地，person_list 为外部清单）。
    """
    ext = _ext(input_path)

    if ext == ".csv":
        from maskit.io.csvio import mask_csv_file

        return mask_csv_file(input_path, output_path, ruleset, pepper, encoding)

    if ext in {".xlsx", ".xls"}:
        from maskit.io.excelio import mask_excel_file

        return mask_excel_file(input_path, output_path, ruleset, pepper)

    if ext in {".json", ".jsonl", ".ndjson"}:
        from maskit.io.jsonio import mask_json_file

        return mask_json_file(input_path, output_path, ruleset, pepper)

    if ext == ".eml":
        from maskit.io.emailio import mask_email_file

        return mask_email_file(input_path, output_path, ruleset, pepper, strategy, scan_names, person_list)

    if ext == ".msg":
        from maskit.io.msgio import mask_msg_file

        return mask_msg_file(input_path, output_path, ruleset, pepper, strategy, scan_names, person_list)

    if ext == ".pdf":
        from maskit.io.pdfio import mask_pdf_file

        return mask_pdf_file(input_path, output_path, ruleset, pepper, strategy, scan_names, person_list)

    if ext == ".docx":
        from maskit.io.docxio import mask_docx_file

        return mask_docx_file(input_path, output_path, ruleset, pepper, strategy, scan_names, person_list)

    raise ValueError(
        f"不支持的输入格式: {ext}（支持 csv/xlsx/xls/json/jsonl/ndjson/eml/msg/pdf/docx）"
    )


SUPPORTED_FORMATS = [".csv", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson", ".eml", ".msg", ".pdf", ".docx"]


def is_text_format(path) -> bool:
    """判断是否为文本格式（全文 PII 扫描）。"""
    return _ext(path) in _TEXT_FORMATS
