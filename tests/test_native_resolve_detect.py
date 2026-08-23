"""N5/N6 differential tests: ConflictResolver and batch detection."""

from __future__ import annotations

import pytest

from maskit.detection.merge import REASON_OUTRANKS, ConflictResolver
from maskit.detection.result import DetectionResult
from maskit.detection.scope import DEFAULT_EMPLOYEE_PREFIXES
from maskit.native import get_backend, native_available, native_unavailable_reason
from maskit.native.fallback import PythonReferenceBackend

pytestmark = pytest.mark.skipif(
    not native_available(), reason=native_unavailable_reason() or "no native"
)

VALID_ID = "110101199003077774"


def _hit(**kwargs) -> dict:
    base = {
        "entity_type": "id_card",
        "original_value": VALID_ID,
        "normalized_value": VALID_ID,
        "confidence": 0.8,
        "recognizer": "regex",
        "reason": "regex",
        "evidence": "regex search",
        "validation_status": "UNKNOWN",
        "start": 0,
        "end": 18,
    }
    base.update(kwargs)
    return base


def test_merge_same_winner_and_reason_code():
    py = PythonReferenceBackend()
    nt = get_backend("native")
    hits = [
        _hit(original_value="110101 19900307 7774", start=0, end=20, confidence=0.8),
        _hit(original_value=VALID_ID, start=0, end=18, confidence=1.0, recognizer="checksum"),
    ]
    a = py.merge_hits(hits, 20)
    b = nt.merge_hits(hits, 20)
    assert list(a["kept"]) == list(b["kept"])
    recs = [
        DetectionResult(
            entity_type=h["entity_type"],
            original_value=h["original_value"],
            normalized_value=h["normalized_value"],
            confidence=h["confidence"],
            recognizer=h["recognizer"],
            reason=h["reason"],
            source="cell",
            start=h["start"],
            end=h["end"],
            evidence=h["evidence"],
        )
        for h in hits
    ]
    ConflictResolver().merge(recs, text_len=20)
    assert b["trace"][0]["reason_code"] == REASON_OUTRANKS


def test_detect_column_batch_phone():
    py = PythonReferenceBackend()
    nt = get_backend("native")
    values = ["13800138000", "2019.06.22", "010-12989966", ""]
    a = py.detect_column_batch(values, "phone", DEFAULT_EMPLOYEE_PREFIXES)
    b = nt.detect_column_batch(values, "phone", DEFAULT_EMPLOYEE_PREFIXES)
    assert [None if x is None else x["entity_type"] for x in a] == [
        None if x is None else x["entity_type"] for x in b
    ]
    assert a[0] is not None and b[0] is not None
    assert a[1] is None and b[1] is None


def test_detect_text_batch_specialized():
    nt = get_backend("native")
    rows = nt.detect_text_batch(
        ["值班座机 010-12989966 勿外拨", "手机 13800138000", "Version 2.5 released"],
        DEFAULT_EMPLOYEE_PREFIXES,
        [],
        False,
    )
    types = [{h["entity_type"] for h in row} for row in rows]
    assert "phone" in types[0]
    assert "phone" in types[1]
    assert "app_version" in types[2]


def test_serial_parallel_hash_consistent(monkeypatch):
    import maskit._native as ext

    values = [f"138{str(i).zfill(8)}" for i in range(400)]
    ext.set_native_threads(1)
    a = ext.hash_batch(values, "maskit-test-pepper-not-production", "v1", [], 8, "1")
    ext.set_native_threads(4)
    b = ext.hash_batch(values, "maskit-test-pepper-not-production", "v1", [], 8, "1")
    ext.set_native_threads(-1)
    assert a == b
