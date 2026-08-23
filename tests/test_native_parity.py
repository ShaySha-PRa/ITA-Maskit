"""Differential tests: Python reference vs native HMAC kernel."""

from __future__ import annotations

import os

import pytest

from maskit.native import get_backend, native_available, native_unavailable_reason
from maskit.native.fallback import PythonReferenceBackend

PEPPER = "maskit-test-pepper-not-production"

CASES = [
    ("", "email"),
    ("13800138000", "phone"),
    ("alice@corp.example", "email"),
    ("张伟", "name"),
    ("司马光华", "name"),
    ("EID-7F3A", "employee_id"),
    ("a" * 4096, "account"),
    ("😀email@x.y", "email"),
]


def test_python_backend_always_available():
    be = PythonReferenceBackend()
    assert be.hash_v1("13800138000", PEPPER, 8) == be.hash_v1("13800138000", PEPPER, 8)


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_import_maskit_native_extension():
    import maskit._native as ext

    assert ext.native_version()
    assert ext.core_abi_version() == 1
    assert "v1" in ext.pseudonym_scheme_versions()


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
@pytest.mark.parametrize("value,entity", CASES)
def test_v1_v2_byte_identical(value, entity):
    py = PythonReferenceBackend()
    nt = get_backend("native")
    assert py.hash_v1(value, PEPPER, 8) == nt.hash_v1(value, PEPPER, 8)
    assert py.hash_v2(value, PEPPER, entity) == nt.hash_v2(value, PEPPER, entity)


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_batch_and_digits_parity():
    py = PythonReferenceBackend()
    nt = get_backend("native")
    values = [v for v, _ in CASES]
    entities = [e for _, e in CASES]
    assert py.hash_batch(values, PEPPER, "v1", length=8) == nt.hash_batch(
        values, PEPPER, "v1", length=8
    )
    assert py.hash_batch(values, PEPPER, "v2", entities, 24) == nt.hash_batch(
        values, PEPPER, "v2", entities, 24
    )
    hx = py.hash_v1("13800138000", PEPPER, 16)
    assert py.digits_from_hex(hx, 11) == nt.digits_from_hex(hx, 11)


@pytest.mark.skipif(not native_available(), reason=native_unavailable_reason() or "no native")
def test_compare_backend():
    os.environ["MASKIT_NATIVE"] = "compare"
    try:
        be = get_backend()
        be.hash_batch(["alice@corp.example", "张伟"], PEPPER, "v2", ["email", "name"], 24)
    finally:
        os.environ.pop("MASKIT_NATIVE", None)


def test_force_native_without_extension(monkeypatch):
    if native_available():
        pytest.skip("extension present")
    monkeypatch.setenv("MASKIT_NATIVE", "1")
    with pytest.raises(RuntimeError, match="unavailable"):
        get_backend()
