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

    def metadata(self) -> dict:
        return {"backend": self.name, "native_version": None}
