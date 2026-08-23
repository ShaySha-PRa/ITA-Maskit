"""Compare Python reference and native outputs; fail on first mismatch."""

from __future__ import annotations


class CompareBackend:
    name = "compare"

    def __init__(self, python_backend, native_backend) -> None:
        self.python = python_backend
        self.native = native_backend

    def hash_v1(self, value: str, pepper: str, length: int = 8) -> str:
        py = self.python.hash_v1(value, pepper, length)
        nt = self.native.hash_v1(value, pepper, length)
        if py != nt:
            raise AssertionError("native/python hash_v1 mismatch")
        return py

    def hash_v2(
        self,
        value: str,
        pepper: str,
        entity_type: str,
        length: int = 24,
        normalizer_version: str = "1",
    ) -> str:
        py = self.python.hash_v2(value, pepper, entity_type, length, normalizer_version)
        nt = self.native.hash_v2(value, pepper, entity_type, length, normalizer_version)
        if py != nt:
            raise AssertionError("native/python hash_v2 mismatch")
        return py

    def hash_batch(
        self,
        values: list[str],
        pepper: str,
        scheme: str = "v1",
        entity_types: list[str] | None = None,
        length: int = 8,
        normalizer_version: str = "1",
    ) -> list[str]:
        kwargs = {
            "values": values,
            "pepper": pepper,
            "scheme": scheme,
            "entity_types": entity_types,
            "length": length,
            "normalizer_version": normalizer_version,
        }
        py = self.python.hash_batch(**kwargs)
        nt = self.native.hash_batch(**kwargs)
        if py != nt:
            raise AssertionError("native/python hash_batch mismatch")
        return py

    def digits_from_hex(self, hex_str: str, n: int) -> str:
        py = self.python.digits_from_hex(hex_str, n)
        nt = self.native.digits_from_hex(hex_str, n)
        if py != nt:
            raise AssertionError("native/python digits_from_hex mismatch")
        return py

    def match_person_list(self, text: str, names) -> list[tuple[int, int, str]]:
        py = self.python.match_person_list(text, names)
        nt = self.native.match_person_list(text, names)
        if py != nt:
            raise AssertionError("native/python match_person_list mismatch")
        return py

    def match_person_list_batch(
        self, texts: list[str], names
    ) -> list[list[tuple[int, int, str]]]:
        py = self.python.match_person_list_batch(texts, names)
        nt = self.native.match_person_list_batch(texts, names)
        if py != nt:
            raise AssertionError("native/python match_person_list_batch mismatch")
        return py

    def to_halfwidth(self, text: str) -> str:
        py = self.python.to_halfwidth(text)
        nt = self.native.to_halfwidth(text)
        if py != nt:
            raise AssertionError("native/python to_halfwidth mismatch")
        return py

    def nfkc_half(self, text: str) -> str:
        py = self.python.nfkc_half(text)
        nt = self.native.nfkc_half(text)
        if py != nt:
            raise AssertionError("native/python nfkc_half mismatch")
        return py

    def id_card_checksum_ok(self, value: str) -> bool:
        py = self.python.id_card_checksum_ok(value)
        nt = self.native.id_card_checksum_ok(value)
        if py != nt:
            raise AssertionError("native/python id_card_checksum_ok mismatch")
        return py

    def luhn_ok(self, digits: str) -> bool:
        py = self.python.luhn_ok(digits)
        nt = self.native.luhn_ok(digits)
        if py != nt:
            raise AssertionError("native/python luhn_ok mismatch")
        return py

    def is_date_like(self, value: str) -> bool:
        py = self.python.is_date_like(value)
        nt = self.native.is_date_like(value)
        if py != nt:
            raise AssertionError("native/python is_date_like mismatch")
        return py

    def is_phone_value(self, value: str, *, column_mode: bool = False) -> bool:
        py = self.python.is_phone_value(value, column_mode=column_mode)
        nt = self.native.is_phone_value(value, column_mode=column_mode)
        if py != nt:
            raise AssertionError("native/python is_phone_value mismatch")
        return py

    def is_app_version_value(self, value: str, *, column_mode: bool = False) -> bool:
        py = self.python.is_app_version_value(value, column_mode=column_mode)
        nt = self.native.is_app_version_value(value, column_mode=column_mode)
        if py != nt:
            raise AssertionError("native/python is_app_version_value mismatch")
        return py

    def looks_like_employee_id(
        self, value: str, prefixes, *, column_mode: bool = False
    ) -> bool:
        py = self.python.looks_like_employee_id(value, prefixes, column_mode=column_mode)
        nt = self.native.looks_like_employee_id(value, prefixes, column_mode=column_mode)
        if py != nt:
            raise AssertionError("native/python looks_like_employee_id mismatch")
        return py

    def classify_phone(self, value: str, *, column_mode: bool = False):
        py = self.python.classify_phone(value, column_mode=column_mode)
        nt = self.native.classify_phone(value, column_mode=column_mode)
        if py != nt:
            raise AssertionError("native/python classify_phone mismatch")
        return py

    def merge_hits(self, hits: list[dict], text_len: int = 0) -> dict:
        py = self.python.merge_hits(hits, text_len)
        nt = self.native.merge_hits(hits, text_len)
        if list(py.get("kept", [])) != list(nt.get("kept", [])):
            raise AssertionError("native/python merge_hits mismatch")
        return py

    def detect_column_batch(
        self, values: list[str], entity_type: str, prefixes=None
    ) -> list:
        py = self.python.detect_column_batch(values, entity_type, prefixes)
        nt = self.native.detect_column_batch(values, entity_type, prefixes)
        if _column_rows(py) != _column_rows(nt):
            raise AssertionError("native/python detect_column_batch mismatch")
        return py

    def detect_text_batch(
        self,
        texts: list[str],
        prefixes=None,
        person_names=None,
        scan_names: bool = False,
    ) -> list:
        py = self.python.detect_text_batch(texts, prefixes, person_names, scan_names)
        nt = self.native.detect_text_batch(texts, prefixes, person_names, scan_names)
        if _text_rows(py) != _text_rows(nt):
            raise AssertionError("native/python detect_text_batch mismatch")
        return py

    def metadata(self) -> dict:
        meta = self.native.metadata()
        meta["backend"] = self.name
        return meta


def _column_rows(rows):
    out = []
    for h in rows:
        if h is None:
            out.append(None)
            continue
        out.append((h.get("entity_type"), h.get("normalized_value"), h.get("subtype")))
    return out


def _text_rows(batches):
    out = []
    for row in batches:
        out.append(
            sorted(
                (
                    h.get("entity_type"),
                    h.get("original_value"),
                    h.get("start"),
                    h.get("end"),
                )
                for h in row
            )
        )
    return out
