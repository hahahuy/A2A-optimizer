from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from ascp._util import _canonical_json


def _bundle_sha256(bundle: list[dict]) -> str:
    digest = hashlib.sha256(_canonical_json(bundle)).hexdigest()
    return f"sha256:{digest}"


@dataclass
class SchemaEntry:
    schema_id: str
    bundle: list[dict]
    registered_at: float
    ttl: int

    @property
    def expires_at(self) -> float:
        return self.registered_at + self.ttl

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


class SchemaRegistry:
    def __init__(self, max_entries: int = 10000) -> None:
        if max_entries <= 0:
            raise ValueError(f"max_entries must be positive, got {max_entries}")
        self._store: dict[str, SchemaEntry] = {}
        self._max_entries = max_entries

    def register(self, bundle: list[dict], ttl: int = 3600) -> tuple[str, int]:
        if not bundle:
            raise ValueError("bundle must not be empty")
        if ttl <= 0:
            raise ValueError(f"ttl must be positive, got {ttl}")

        schema_id = _bundle_sha256(bundle)
        now = time.time()

        if schema_id in self._store:
            entry = self._store[schema_id]
            entry.registered_at = now
            entry.ttl = ttl
        else:
            # Evict expired entries at capacity; if still full, evict the oldest entry
            if len(self._store) >= self._max_entries:
                self.evict_expired()
                # Hard eviction: if still at/over cap, remove the oldest entry
                if len(self._store) >= self._max_entries:
                    oldest_id = min(self._store, key=lambda sid: self._store[sid].registered_at)
                    del self._store[oldest_id]
            self._store[schema_id] = SchemaEntry(
                schema_id=schema_id,
                bundle=list(bundle),
                registered_at=now,
                ttl=ttl,
            )

        return schema_id, ttl

    def resolve(self, schema_id: str) -> list[dict]:
        entry = self._store.get(schema_id)
        if entry is None or entry.is_expired:
            raise KeyError(schema_id)
        return list(entry.bundle)

    def refresh(self, schema_id: str, ttl: int = 3600) -> int:
        if ttl <= 0:
            raise ValueError(f"ttl must be positive, got {ttl}")
        entry = self._store.get(schema_id)
        if entry is None or entry.is_expired:
            raise KeyError(schema_id)
        entry.registered_at = time.time()
        entry.ttl = ttl
        return ttl

    def evict_expired(self) -> int:
        expired = [sid for sid, e in self._store.items() if e.is_expired]
        for sid in expired:
            del self._store[sid]
        return len(expired)

    def __len__(self) -> int:
        return sum(1 for e in self._store.values() if not e.is_expired)
