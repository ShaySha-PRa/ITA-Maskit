"""Detection layer: recognizers emit DetectionResult; transformation stays in rules.engine."""

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.merge import ConflictResolver
from maskit.detection.pipeline import detect_cell, detect_text
from maskit.detection.registry import RecognizerRegistry
from maskit.detection.result import DetectionResult, confidence_band

__all__ = [
    "ConflictResolver",
    "DetectContext",
    "DetectionResult",
    "Recognizer",
    "RecognizerRegistry",
    "confidence_band",
    "detect_cell",
    "detect_text",
]
