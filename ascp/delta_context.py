import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from ascp._util import _canonical_json


@dataclass
class Message:
    role: str
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Checkpoint:
    checkpoint_id: str
    messages: list[Message]
    created_at: float
    label: str = ""


def _message_to_dict(msg: Message) -> dict:
    return {"content": msg.content, "metadata": msg.metadata, "role": msg.role}


def _message_hash(msg: Message) -> str:
    return hashlib.sha256(_canonical_json(_message_to_dict(msg))).hexdigest()


def _messages_id(messages: list[Message]) -> str:
    payload = [_message_to_dict(m) for m in messages]
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return f"sha256:{digest}"


class DeltaContextManager:
    def __init__(self, max_checkpoints: int = 1000) -> None:
        if max_checkpoints <= 0:
            raise ValueError(f"max_checkpoints must be positive, got {max_checkpoints}")
        self._max_checkpoints = max_checkpoints
        self._cache: OrderedDict[str, Checkpoint] = OrderedDict()

    def checkpoint(self, messages: list[Message], label: str = "") -> Checkpoint:
        if not messages:
            raise ValueError("messages must not be empty")
        cid = _messages_id(messages)
        if cid in self._cache:
            self._cache.move_to_end(cid)
            return self._cache[cid]
        cp = Checkpoint(
            checkpoint_id=cid,
            messages=list(messages),
            created_at=time.time(),
            label=label,
        )
        self._cache[cid] = cp
        while len(self._cache) > self._max_checkpoints:
            self._cache.popitem(last=False)
        return cp

    def delta(self, since: Checkpoint, current: list[Message]) -> list[Message]:
        n = len(since.messages)
        if len(current) < n:
            raise ValueError(
                f"current history has {len(current)} messages, fewer than checkpoint ({n})"
            )
        for i, (cp_msg, cur_msg) in enumerate(zip(since.messages, current)):
            if _message_hash(cp_msg) != _message_hash(cur_msg):
                raise ValueError(
                    f"history diverges at index {i}: checkpoint message differs from current"
                )
        return list(current[n:])

    def reconstruct(self, checkpoint: Checkpoint, delta: list[Message]) -> list[Message]:
        existing_hashes = {_message_hash(m) for m in checkpoint.messages}
        for msg in delta:
            if _message_hash(msg) in existing_hashes:
                raise ValueError(
                    f"duplicate message detected in delta: role={msg.role!r} content={msg.content!r}"
                )
        return list(checkpoint.messages) + list(delta)

    def message_savings(self, checkpoint: Checkpoint, current: list[Message]) -> dict:
        full = len(current)
        saved = len(checkpoint.messages)
        delta_count = full - saved
        saved_message_pct = (saved / full * 100.0) if full > 0 else 0.0
        return {
            "full_message_count": full,
            "delta_count": delta_count,
            "saved_count": saved,
            "saved_message_pct": saved_message_pct,
        }
