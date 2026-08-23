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

    def metadata(self) -> dict:
        meta = self.native.metadata()
        meta["backend"] = self.name
        return meta
