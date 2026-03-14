"""Content-Addressed Artifact Store — Tool 2 of the ASCP library."""

import dataclasses
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class ArtifactEntry:
    cid: str
    content: bytes
    size: int
    stored_at: float
    media_type: str


class ArtifactStore:
    """In-memory content-addressed store with LRU eviction."""

    def __init__(self, max_bytes: int = 100 * 1024 * 1024) -> None:
        self._max_bytes = max_bytes
        # OrderedDict keyed by CID; order = insertion/access order (LRU at front)
        self._entries: OrderedDict[str, ArtifactEntry] = OrderedDict()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, content: bytes | str, media_type: str = "text/plain") -> str:
        if isinstance(content, str):
            content = content.encode("utf-8")

        if len(content) == 0:
            raise ValueError("content must not be empty")

        if len(content) > self._max_bytes:
            raise ValueError(
                f"content size {len(content)} exceeds max_bytes {self._max_bytes}"
            )

        cid = "sha256:" + hashlib.sha256(content).hexdigest()
        now = time.time()

        if cid in self._entries:
            # Refresh access order (move to end = most recently used)
            self._entries.move_to_end(cid)
            return cid

        entry = ArtifactEntry(
            cid=cid,
            content=content,
            size=len(content),
            stored_at=now,
            media_type=media_type,
        )
        self._entries[cid] = entry

        if self.total_bytes > self._max_bytes:
            self.evict_lru()

        return cid

    def retrieve(self, cid: str) -> ArtifactEntry:
        if cid not in self._entries:
            raise KeyError(cid)
        # Refresh access order
        self._entries.move_to_end(cid)
        return dataclasses.replace(self._entries[cid])

    def delete(self, cid: str) -> bool:
        if cid not in self._entries:
            return False
        del self._entries[cid]
        return True

    def evict_lru(self, target_bytes: int | None = None) -> int:
        if target_bytes is None:
            target_bytes = self._max_bytes

        evicted = 0
        while self._entries and self.total_bytes > target_bytes:
            # The first item in OrderedDict is the least recently used
            lru_cid, _ = next(iter(self._entries.items()))
            del self._entries[lru_cid]
            evicted += 1

        return evicted

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def total_bytes(self) -> int:
        return sum(e.size for e in self._entries.values())

    @property
    def count(self) -> int:
        return len(self._entries)
