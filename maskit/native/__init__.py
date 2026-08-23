"""Optional native backend. Default is auto: use C++ if the extension imported."""

from __future__ import annotations

import os

from maskit.native.adapter import NativeBackend
from maskit.native.fallback import PythonReferenceBackend

_NATIVE_UNAVAILABLE: str | None = None
try:
    import maskit._native as _ext  # type: ignore[attr-defined]
except (ImportError, OSError) as exc:  # pragma: no cover - missing extension is expected
    _ext = None
    _NATIVE_UNAVAILABLE = f"{type(exc).__name__}: {exc}"


def native_available() -> bool:
    return _ext is not None


def native_unavailable_reason() -> str | None:
    return _NATIVE_UNAVAILABLE


def resolve_mode(mode: str | None = None) -> str:
    raw = (mode or os.environ.get("MASKIT_NATIVE") or "auto").strip().lower()
    if raw in {"0", "false", "python", "off"}:
        return "python"
    if raw in {"1", "true", "native", "on"}:
        return "native"
    if raw == "compare":
        return "compare"
    return "auto"


def get_backend(mode: str | None = None):
    resolved = resolve_mode(mode)
    if resolved == "python":
        return PythonReferenceBackend()
    if resolved == "native":
        if _ext is None:
            raise RuntimeError(
                "MASKIT_NATIVE=1 but native extension is unavailable: "
                f"{_NATIVE_UNAVAILABLE}"
            )
        return NativeBackend(_ext)
    if resolved == "auto":
        if _ext is None:
            return PythonReferenceBackend()
        return NativeBackend(_ext)
    if resolved == "compare":
        if _ext is None:
            raise RuntimeError(
                "native-mode=compare requires the extension: "
                f"{_NATIVE_UNAVAILABLE}"
            )
        from maskit.native.parity import CompareBackend

        return CompareBackend(PythonReferenceBackend(), NativeBackend(_ext))
    raise ValueError(f"unknown native mode: {resolved}")


__all__ = [
    "NativeBackend",
    "PythonReferenceBackend",
    "get_backend",
    "native_available",
    "native_unavailable_reason",
    "resolve_mode",
]
