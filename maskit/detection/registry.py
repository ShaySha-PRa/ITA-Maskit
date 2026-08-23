"""Registry: run a list of recognizers and merge their DetectionResult lists."""

from __future__ import annotations

from maskit.detection.base import DetectContext, Recognizer
from maskit.detection.merge import ConflictResolver
from maskit.detection.result import DetectionResult


class RecognizerRegistry:
    def __init__(
        self,
        recognizers: list[Recognizer] | None = None,
        resolver: ConflictResolver | None = None,
    ):
        self._recognizers = list(recognizers or [])
        self.resolver = resolver or ConflictResolver()

    def add(self, recognizer: Recognizer) -> None:
        self._recognizers.append(recognizer)

    def recognizers(self) -> tuple[Recognizer, ...]:
        return tuple(self._recognizers)

    def detect(self, text: str, ctx: DetectContext, *, merge: bool = True) -> list[DetectionResult]:
        raw: list[DetectionResult] = []
        for rec in self._recognizers:
            raw.extend(rec.detect(text, ctx))
        if merge:
            return self.resolver.merge(raw, text_len=len(text))
        return raw
