from __future__ import annotations

import json


def _canonical_json(obj: object) -> bytes:
    """Serialize obj to canonical JSON: keys sorted, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
