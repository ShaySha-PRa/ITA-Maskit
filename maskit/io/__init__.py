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
    image_crop: bool = False,
    details: dict | None = None,
) -> int:
    """统一脱敏入口：按扩展名分发，返回处理行数/页数/段数。

    表格格式（CSV/Excel/JSON）：按列脱敏，strategy 由 ruleset 每列决定。
    文本格式（邮件/PDF/Word）：全文 PII 扫描，strategy 参数指定。
    图片格式（PNG/JPG，beta）：需 image_crop=True 启用 OCR 裁剪。
    details（可选）：传 dict 时记录格式相关的处理详情（如 Excel 各 sheet 信息）。
    """
    ext = _ext(input_path)

    if ext == ".csv":
        from maskit.io.csvio import mask_csv_file

        return mask_csv_file(input_path, output_path, ruleset, pepper, encoding)

    if ext in {".xlsx", ".xls"}:
        from maskit.io.excelio import mask_excel_file

        return mask_excel_file(input_path, output_path, ruleset, pepper, details)

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

    if ext in {".png", ".jpg", ".jpeg"}:
        if not image_crop:
            raise ValueError(
                f"图片脱敏是 beta 功能，需 --image-crop 显式启用（并安装 tesseract OCR）。"
                f"输入: {input_path}"
            )
        from maskit.io.imageio import mask_image_file

        return mask_image_file(input_path, output_path, ruleset, pepper, strategy)

    raise ValueError(
        f"不支持的输入格式: {ext}（支持 csv/xlsx/xls/json/jsonl/ndjson/eml/msg/pdf/docx）"
    )


SUPPORTED_FORMATS = [
    ".csv", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson",
    ".eml", ".msg", ".pdf", ".docx",
    ".png", ".jpg", ".jpeg",  # beta：需 --image-crop
]


def is_text_format(path) -> bool:
    """判断是否为文本格式（全文 PII 扫描）。"""
    return _ext(path) in _TEXT_FORMATS


def is_image_format(path) -> bool:
    """判断是否为图片格式（beta 裁剪脱敏）。"""
    return _ext(path) in {".png", ".jpg", ".jpeg"}


def discover_files(path: str | Path) -> list[str]:
    """发现待脱敏文件。

    - 输入是文件 → 返回 [该文件]
    - 输入是文件夹 → 递归扫描支持的扩展名（SUPPORTED_FORMATS）
    - 支持的扩展名由 SUPPORTED_FORMATS 决定
    """
    p = Path(path)
    if p.is_file():
        return [str(p)]
    if p.is_dir():
        files = []
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS:
                files.append(str(f))
        return files
    raise ValueError(f"路径不存在: {path}")


def validate_files(paths: list[str]) -> tuple[list[str], list[dict]]:
    """校验文件列表（GUI 防传错用）。

    返回 (有效文件, 无效文件信息[{path, reason}])。
    - 不存在的路径 → 无效
    - 文件扩展名不在 SUPPORTED_FORMATS → 无效
    - 文件夹 → 用 discover_files 展开（有效文件加入）
    """
    valid: list[str] = []
    invalid: list[dict] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            invalid.append({"path": p, "reason": "路径不存在"})
            continue
        if path.is_dir():
            try:
                valid.extend(discover_files(p))
            except ValueError as exc:
                invalid.append({"path": p, "reason": str(exc)})
            continue
        if path.is_file():
            if path.suffix.lower() in SUPPORTED_FORMATS:
                valid.append(str(path))
            else:
                invalid.append({"path": p, "reason": f"不支持的文件类型 {path.suffix}"})
    return valid, invalid


def default_output_path(input_path: str, output_dir: str | None = None) -> str:
    """生成输出路径。

    - output_dir 指定 → 输出到该目录（同名 + _masked 后缀）
    - 未指定 → 输入同目录（当前行为）
    """
    src = Path(input_path)
    out_name = src.stem + "_masked" + src.suffix
    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        return str(out_dir / out_name)
    return str(src.with_name(out_name))
