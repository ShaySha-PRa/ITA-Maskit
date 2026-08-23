"""N2/N3 differential tests: validators and halfwidth/canonical forms."""

from __future__ import annotations

import pytest

from maskit.detection.scope import DEFAULT_EMPLOYEE_PREFIXES
from maskit.native import get_backend, native_available, native_unavailable_reason
from maskit.native.fallback import PythonReferenceBackend

pytestmark = pytest.mark.skipif(
    not native_available(), reason=native_unavailable_reason() or "no native"
)

PHONES = [
    "13800138000",
    "138-0013-8000",
    "138 0013 8000",
    "+86 13800138000",
    "0086-13800138000",
    "１３８００１３８０００",
    "010-12989966",
    "0755-5707154",
    "2019.06.22",
    "2022-02-28",
    "",
    "0.8",
]
IDS = ["110101199003077774", "110101199003077777", "110101 19900307 7774", "123"]
BANKS = ["4111111111111111", "6222021234567890", "123"]
VERSIONS = ["v1.2.3", "1.4.2", "2024.1.1", "v2.5", "13.08"]
EIDS = ["EID-10001", "ISO-8601", "RFC-2119", "CVE-2024", "JIRA-1001", "010-12989966"]


def test_checksum_and_date_phone_parity():
    py = PythonReferenceBackend()
    nt = get_backend("native")
    for value in IDS:
        assert py.id_card_checksum_ok(value) == nt.id_card_checksum_ok(value), value
    for value in BANKS:
        assert py.luhn_ok(value) == nt.luhn_ok(value), value
    for value in PHONES:
        assert py.is_date_like(value) == nt.is_date_like(value), value
        assert py.is_phone_value(value, column_mode=True) == nt.is_phone_value(
            value, column_mode=True
        ), value
        assert py.classify_phone(value, column_mode=True) == nt.classify_phone(
            value, column_mode=True
        ), value
        assert py.classify_phone(value, column_mode=False) == nt.classify_phone(
            value, column_mode=False
        ), value


def test_version_employee_parity():
    py = PythonReferenceBackend()
    nt = get_backend("native")
    for value in VERSIONS:
        assert py.is_app_version_value(value, column_mode=True) == nt.is_app_version_value(
            value, column_mode=True
        ), value
        assert py.is_app_version_value(value, column_mode=False) == nt.is_app_version_value(
            value, column_mode=False
        ), value
    for value in EIDS:
        assert py.looks_like_employee_id(
            value, DEFAULT_EMPLOYEE_PREFIXES, column_mode=False
        ) == nt.looks_like_employee_id(
            value, DEFAULT_EMPLOYEE_PREFIXES, column_mode=False
        ), value


def test_normalize_parity():
    py = PythonReferenceBackend()
    nt = get_backend("native")
    for value in ("ＡＢＣ", "１３８", "a@ｂ.com", "  x  ", "alice@corp.example"):
        assert py.to_halfwidth(value) == nt.to_halfwidth(value), value
        assert py.nfkc_half(value) == nt.nfkc_half(value), value
        assert py.canonical_phone(value) == nt.canonical_phone(value), value
