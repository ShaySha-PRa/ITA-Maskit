"""Python reference HMAC / digit derivation. Kept for fallback and parity."""

from __future__ import annotations

from maskit.rules.engine import digits_from_hex as _digits_from_hex
from maskit.rules.engine import pseudo_hash, pseudo_hash_v2


class PythonReferenceBackend:
    name = "python"

    def hash_v1(self, value: str, pepper: str, length: int = 8) -> str:
        return pseudo_hash(value, pepper, length)

    def hash_v2(
        self,
        value: str,
        pepper: str,
        entity_type: str,
        length: int = 24,
        normalizer_version: str = "1",
    ) -> str:
        return pseudo_hash_v2(
            value,
            pepper,
            entity_type,
            length=length,
            normalizer_version=normalizer_version,
        )

    def hash_batch(
        self,
        values: list[str],
        pepper: str,
        scheme: str = "v1",
        entity_types: list[str] | None = None,
        length: int = 8,
        normalizer_version: str = "1",
    ) -> list[str]:
        entity_types = entity_types or []
        out: list[str] = []
        if scheme == "v1":
            return [self.hash_v1(v, pepper, length) for v in values]
        if scheme != "v2":
            raise ValueError("unsupported pseudonym scheme")
        for i, value in enumerate(values):
            if len(entity_types) == 1:
                entity = entity_types[0]
            elif len(entity_types) == len(values):
                entity = entity_types[i]
            else:
                entity = "unknown"
            out.append(
                self.hash_v2(value, pepper, entity, length, normalizer_version)
            )
        return out

    def digits_from_hex(self, hex_str: str, n: int) -> str:
        return _digits_from_hex(hex_str, n)

    def match_person_list(self, text: str, names) -> list[tuple[int, int, str]]:
        from maskit.rules.name_company import iter_person_list_spans_ref

        return iter_person_list_spans_ref(text, set(names) if names else set())

    def match_person_list_batch(
        self, texts: list[str], names
    ) -> list[list[tuple[int, int, str]]]:
        return [self.match_person_list(t, names) for t in texts]

    def to_halfwidth(self, text: str) -> str:
        from maskit.detection.canonical import to_halfwidth

        return to_halfwidth(text)

    def nfkc_half(self, text: str) -> str:
        from maskit.detection.phone import nfkc_half

        return nfkc_half(text)

    def canonical_phone(self, text: str) -> str:
        from maskit.detection.phone import canonical_phone

        return canonical_phone(text)

    def id_card_checksum_ok(self, value: str) -> bool:
        from maskit.detection.checksum import id_card_checksum_ok

        return id_card_checksum_ok(value)

    def luhn_ok(self, digits: str) -> bool:
        from maskit.detection.checksum import luhn_ok

        return luhn_ok(digits)

    def is_date_like(self, value: str) -> bool:
        from maskit.detection.phone import is_date_like

        return is_date_like(value)

    def is_phone_value(self, value: str, *, column_mode: bool = False) -> bool:
        from maskit.detection.phone import is_phone_value

        return is_phone_value(value, column_mode=column_mode)

    def is_app_version_value(self, value: str, *, column_mode: bool = False) -> bool:
        from maskit.detection.version import is_app_version_value

        return is_app_version_value(value, column_mode=column_mode)

    def looks_like_employee_id(
        self, value: str, prefixes, *, column_mode: bool = False
    ) -> bool:
        from maskit.detection.employee import looks_like_employee_id

        return looks_like_employee_id(value, tuple(prefixes), column_mode=column_mode)

    def classify_phone(self, value: str, *, column_mode: bool = False):
        from maskit.detection.phone import classify_phone

        return classify_phone(value, column_mode=column_mode)

    def merge_hits(self, hits: list[dict], text_len: int = 0) -> dict:
        from maskit.detection.merge import ConflictResolver
        from maskit.detection.result import DetectionResult

        recs = []
        for h in hits:
            recs.append(
                DetectionResult(
                    entity_type=h["entity_type"],
                    original_value=h["original_value"],
                    normalized_value=h.get("normalized_value", h["original_value"]),
                    confidence=float(h.get("confidence", 0.0)),
                    recognizer=h.get("recognizer", ""),
                    reason=h.get("reason", ""),
                    source=h.get("source", "cell"),
                    start=h.get("start"),
                    end=h.get("end"),
                    evidence=h.get("evidence", ""),
                    validation_status=h.get("validation_status", "UNKNOWN"),
                    subtype=h.get("subtype", ""),
                )
            )
        resolver = ConflictResolver()
        kept = resolver.merge(recs, text_len=text_len)
        kept_set = {id(r) for r in kept}
        kept_idx = [i for i, r in enumerate(recs) if id(r) in kept_set]
        return {"kept": kept_idx, "trace": resolver.last_trace}

    def detect_column_batch(
        self, values: list[str], entity_type: str, prefixes=None
    ) -> list:
        from maskit.detection.pipeline import detect_cell
        from maskit.rules.loader import load_ruleset

        rs = load_ruleset()
        rule = rs.defs.get(entity_type)
        out = []
        for v in values:
            hits = detect_cell(v, ruleset=rs, mapped_rule=rule, value_scan=False)
            typed = [h for h in hits if h.entity_type == entity_type]
            if not typed:
                out.append(None)
                continue
            h = typed[0]
            out.append(
                {
                    "entity_type": h.entity_type,
                    "original_value": h.original_value,
                    "normalized_value": h.normalized_value,
                    "confidence": h.confidence,
                    "recognizer": h.recognizer,
                    "reason": h.reason,
                    "evidence": h.evidence,
                    "validation_status": h.validation_status,
                    "subtype": h.subtype,
                    "start": h.start,
                    "end": h.end,
                }
            )
        return out

    def detect_text_batch(
        self,
        texts: list[str],
        prefixes=None,
        person_names=None,
        scan_names: bool = False,
    ) -> list:
        from maskit.detection.pipeline import detect_text
        from maskit.rules.loader import load_ruleset

        rs = load_ruleset()
        names = set(person_names or ())
        out = []
        for text in texts:
            hits = detect_text(
                text, ruleset=rs, person_list=names or None, scan_names=scan_names
            )
            out.append(
                [
                    {
                        "entity_type": h.entity_type,
                        "original_value": h.original_value,
                        "normalized_value": h.normalized_value,
                        "confidence": h.confidence,
                        "recognizer": h.recognizer,
                        "reason": h.reason,
                        "evidence": h.evidence,
                        "validation_status": h.validation_status,
                        "subtype": h.subtype,
                        "start": h.start,
                        "end": h.end,
                    }
                    for h in hits
                    if h.entity_type in {"phone", "employee_id", "app_version"}
                ]
            )
        return out

    def metadata(self) -> dict:
        return {"backend": self.name, "native_version": None}
