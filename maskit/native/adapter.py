"""Thin wrapper over maskit._native. Does not hold Python objects in C++."""

from __future__ import annotations


class NativeBackend:
    name = "native"

    def __init__(self, ext) -> None:
        self._ext = ext
        self._dicts: dict[frozenset[str], object] = {}

    def _compiled(self, names) -> object:
        key = frozenset(n for n in names if n)
        compiled = self._dicts.get(key)
        if compiled is None:
            compiled = self._ext.compile_person_list(sorted(key))
            self._dicts[key] = compiled
        return compiled

    def hash_v1(self, value: str, pepper: str, length: int = 8) -> str:
        return self._ext.hash_v1(value, pepper, length)

    def hash_v2(
        self,
        value: str,
        pepper: str,
        entity_type: str,
        length: int = 24,
        normalizer_version: str = "1",
    ) -> str:
        return self._ext.hash_v2(value, pepper, entity_type, length, normalizer_version)

    def hash_batch(
        self,
        values: list[str],
        pepper: str,
        scheme: str = "v1",
        entity_types: list[str] | None = None,
        length: int = 8,
        normalizer_version: str = "1",
    ) -> list[str]:
        return self._ext.hash_batch(
            values,
            pepper,
            scheme,
            entity_types or [],
            length,
            normalizer_version,
        )

    def digits_from_hex(self, hex_str: str, n: int) -> str:
        return self._ext.digits_from_hex(hex_str, n)

    def match_person_list(self, text: str, names) -> list[tuple[int, int, str]]:
        compiled = self._compiled(names)
        return [(int(s), int(e), n) for s, e, n in compiled.match(text)]

    def match_person_list_batch(
        self, texts: list[str], names
    ) -> list[list[tuple[int, int, str]]]:
        compiled = self._compiled(names)
        return [
            [(int(s), int(e), n) for s, e, n in row]
            for row in compiled.match_batch(texts)
        ]

    def to_halfwidth(self, text: str) -> str:
        return self._ext.to_halfwidth(text)

    def nfkc_half(self, text: str) -> str:
        return self._ext.nfkc_half(text)

    def canonical_phone(self, text: str) -> str:
        return self._ext.canonical_phone(text)

    def id_card_checksum_ok(self, value: str) -> bool:
        return bool(self._ext.id_card_checksum_ok(value))

    def luhn_ok(self, digits: str) -> bool:
        return bool(self._ext.luhn_ok(digits))

    def is_date_like(self, value: str) -> bool:
        return bool(self._ext.is_date_like(value))

    def is_phone_value(self, value: str, *, column_mode: bool = False) -> bool:
        return bool(self._ext.is_phone_value(value, column_mode))

    def is_app_version_value(self, value: str, *, column_mode: bool = False) -> bool:
        return bool(self._ext.is_app_version_value(value, column_mode))

    def looks_like_employee_id(
        self, value: str, prefixes, *, column_mode: bool = False
    ) -> bool:
        return bool(self._ext.looks_like_employee_id(value, list(prefixes), column_mode))

    def classify_phone(self, value: str, *, column_mode: bool = False):
        return self._ext.classify_phone(value, column_mode)

    def merge_hits(self, hits: list[dict], text_len: int = 0) -> dict:
        return self._ext.merge_hits(hits, text_len)

    def detect_column_batch(
        self, values: list[str], entity_type: str, prefixes=None
    ) -> list:
        return self._ext.detect_column_batch(values, entity_type, list(prefixes or ()))

    def detect_text_batch(
        self,
        texts: list[str],
        prefixes=None,
        person_names=None,
        scan_names: bool = False,
    ) -> list:
        compiled = self._compiled(person_names) if (scan_names and person_names) else None
        return self._ext.detect_text_batch(
            texts, list(prefixes or ()), compiled, bool(scan_names and compiled)
        )

    def metadata(self) -> dict:
        return {
            "backend": self.name,
            "native_version": self._ext.native_version(),
            "core_abi_version": self._ext.core_abi_version(),
            "detector_version": self._ext.detector_version(),
            "pseudonym_scheme_versions": list(self._ext.pseudonym_scheme_versions()),
            "build_compiler": self._ext.build_compiler(),
            "build_type": self._ext.build_type(),
            "native_threads": int(self._ext.native_threads()),
        }
