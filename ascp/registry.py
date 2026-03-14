from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field


def _canonical_json(obj: object) -> bytes:
    """Serialize obj to canonical JSON: keys sorted, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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
    def __init__(self) -> None:
        self._store: dict[str, SchemaEntry] = {}

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
