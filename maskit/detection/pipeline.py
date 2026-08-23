"""Orchestrate recognizers for one cell or a document text chunk.

Does not transform. Engine applies mask/pseudo to DetectionResult lists.
"""

from __future__ import annotations

from maskit.detection.base import DetectContext
from maskit.detection.checksum import ChecksumRecognizer, annotate_with_checksum
from maskit.detection.column import ColumnRecognizer
from maskit.detection.dictionary import DictionaryRecognizer
from maskit.detection.employee import EmployeeIdRecognizer
from maskit.detection.merge import ConflictResolver
from maskit.detection.phone import PhoneRecognizer
from maskit.detection.regex import RegexRecognizer
from maskit.detection.result import DetectionResult
from maskit.detection.version import AppVersionRecognizer
from maskit.rules.defs import RuleDef, RuleSet

_RESOLVER = ConflictResolver()
_COLUMN = ColumnRecognizer()
_REGEX_FULL = RegexRecognizer("fullmatch")
_REGEX_SEARCH = RegexRecognizer("search")
_DICT_EXACT = DictionaryRecognizer("exact")
_DICT_SPAN = DictionaryRecognizer("span")
_CHECKSUM = ChecksumRecognizer()
_PHONE = PhoneRecognizer()
_EID = EmployeeIdRecognizer()
_VER = AppVersionRecognizer()


def _annotate_id_bank(hits: list[DetectionResult]) -> list[DetectionResult]:
    out: list[DetectionResult] = []
    for h in hits:
        if h.entity_type in {"id_card", "bank_card"}:
            out.append(annotate_with_checksum(h))
        else:
            out.append(h)
    return out


def detect_cell(
    value: str,
    *,
    ruleset: RuleSet,
    mapped_rule: RuleDef | None = None,
    person_list: set[str] | None = None,
    value_scan: bool = True,
    column: str | None = None,
    sheet: str | None = None,
) -> list[DetectionResult]:
    """Structured cell: column fullmatch → whole-cell scan → in-cell spans."""
    raw = value if value is not None else ""
    if not str(raw).strip():
        return []
    s = str(raw)
    if s.strip().startswith("="):
        return []

    ctx = DetectContext(
        ruleset=ruleset,
        column=column,
        mapped_rule=mapped_rule,
        person_list=person_list,
        source="cell",
        sheet=sheet,
        path="structured",
    )
    specialized = _PHONE.detect(s, ctx) + _EID.detect(s, ctx) + _VER.detect(s, ctx)
    col_hits = _COLUMN.detect(s, ctx)
    if col_hits:
        return _annotate_id_bank(_RESOLVER.merge(col_hits + specialized, text_len=len(s)))
    if specialized and mapped_rule is not None:
        return _annotate_id_bank(_RESOLVER.merge(specialized, text_len=len(s)))
    if not value_scan:
        return []

    whole = _RESOLVER.merge(
        _REGEX_FULL.detect(s, ctx) + _DICT_EXACT.detect(s, ctx) + specialized,
        text_len=len(s),
    )
    if whole:
        return _annotate_id_bank(whole)

    inner = _RESOLVER.merge(
        _REGEX_SEARCH.detect(s, ctx) + _DICT_SPAN.detect(s, ctx) + specialized,
        text_len=len(s),
    )
    return _annotate_id_bank(inner)


def detect_text(
    text: str,
    *,
    ruleset: RuleSet,
    person_list: set[str] | None = None,
    scan_names: bool = False,
    page: int | None = None,
) -> list[DetectionResult]:
    """Unstructured document path. No column matching."""
    if not text:
        return []
    ctx = DetectContext(
        ruleset=ruleset,
        person_list=person_list,
        scan_names=scan_names,
        source="text",
        page=page,
        path="document",
    )
    raw = _REGEX_SEARCH.detect(text, ctx)
    raw.extend(_PHONE.detect(text, ctx))
    raw.extend(_EID.detect(text, ctx))
    raw.extend(_VER.detect(text, ctx))
    if scan_names:
        raw.extend(_DICT_SPAN.detect(text, ctx))
    raw.extend(_CHECKSUM.detect(text, ctx))
    return _annotate_id_bank(_RESOLVER.merge(raw, text_len=len(text)))
