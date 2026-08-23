"""Allowlist for business exceptions. Not a substitute for broken recognizers."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


def default_allowlist_path() -> Path:
    override = os.environ.get("MASKIT_ALLOWLIST")
    if override:
        return Path(override)
    return Path.home() / ".maskit" / "allowlist.json"


@dataclass
class AllowlistEntry:
    entity_type: str
    match_mode: str  # exact | fingerprint
    value: str
    scope: str  # global | ruleset | document
    reason: str
    created_at: str
    expiry: str | None = None


class Allowlist:
    def __init__(self, entries: list[AllowlistEntry] | None = None):
        self.entries = entries or []

    @classmethod
    def load(cls, path: str | Path) -> Allowlist:
        p = Path(path)
        if not p.exists():
            return cls([])
        raw = json.loads(p.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("entries") or []
        return cls([AllowlistEntry(**row) for row in items])

    def allows(self, entity_type: str, value: str, *, fingerprint: str | None = None) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        for e in self.entries:
            if e.entity_type != entity_type:
                continue
            if e.expiry and e.expiry < now:
                continue
            if e.match_mode == "exact" and e.value == value:
                return True
            if e.match_mode == "fingerprint" and fingerprint and e.value == fingerprint:
                return True
        return False

    def add_fingerprint(
        self,
        entity_type: str,
        fingerprint: str,
        *,
        reason: str = "review workbench",
        scope: str = "global",
    ) -> None:
        if self.allows(entity_type, "", fingerprint=fingerprint):
            return
        self.entries.append(
            AllowlistEntry(
                entity_type=entity_type,
                match_mode="fingerprint",
                value=fingerprint,
                scope=scope,
                reason=reason,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    def save(self, path: str | Path | None = None) -> Path:
        dest = Path(path) if path else default_allowlist_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(
                {"entries": [asdict(e) for e in self.entries]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return dest
