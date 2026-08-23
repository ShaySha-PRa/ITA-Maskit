"""Thin wrapper over maskit._native. Does not hold Python objects in C++."""

from __future__ import annotations


class NativeBackend:
    name = "native"

    def __init__(self, ext) -> None:
        self._ext = ext

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

    def metadata(self) -> dict:
        return {
            "backend": self.name,
            "native_version": self._ext.native_version(),
            "core_abi_version": self._ext.core_abi_version(),
            "detector_version": self._ext.detector_version(),
            "pseudonym_scheme_versions": list(self._ext.pseudonym_scheme_versions()),
            "build_compiler": self._ext.build_compiler(),
            "build_type": self._ext.build_type(),
        }
