"""Detection scope, mode, validation, and write decisions.

text_scanable is not enough: weak rules must not free-scan document/OCR.
"""

from __future__ import annotations

from enum import Enum

DETECTOR_VERSION = "2.0"

# YAML regex may free-scan only these types (strong features).
FREE_SCAN_TYPES = frozenset({"email", "ip", "id_card", "bank_card"})
# Dedicated recognizers; never use unanchored YAML match in document/OCR.
SPECIALIZED_TYPES = frozenset({"phone", "employee_id", "app_version"})

DEFAULT_EMPLOYEE_PREFIXES = ("EID", "EMP", "STAFF")


class DetectionScope(str, Enum):
    DOCUMENT = "document"
    OCR = "ocr"
    COLUMN_INFERRED = "column_inferred"
    COLUMN_EXPLICIT = "column_explicit"
    CELL = "cell"


class DetectionMode(str, Enum):
    FREE_SCAN = "free_scan"
    CONTEXTUAL = "contextual"
    VALIDATED = "validated"
    FORCE = "force"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class DecisionAction(str, Enum):
    AUTO_APPLY = "AUTO_APPLY"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


class ChecksumPolicy(str, Enum):
    """How INVALID id_card / bank_card checksums are written."""

    LEGACY = "legacy"  # historical: still mask (tests / old CLI)
    REVIEW = "review"  # do not auto-write; emit review
    STRICT = "strict"  # review + block final output if unresolved
