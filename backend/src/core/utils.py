import hashlib
import os
from typing import Any


def resolve_path(path: str) -> str | None:
    """Resolve a path by trying both direct and backend/ prefixed versions."""
    possible_paths = [path, os.path.join("backend", path)]
    for p in possible_paths:
        if os.path.isfile(p):
            return p
    return None


def string_to_bigint(s: Any) -> int:
    if s is None:
        return 0
    if isinstance(s, int):
        return s
    s_str = str(s).strip()
    if s_str.isdigit():
        return int(s_str)
    if s_str.startswith("-") and s_str[1:].isdigit():
        return int(s_str)

    # Hash non-numeric strings to a signed 64-bit integer
    h = hashlib.sha256(s_str.encode("utf-8")).digest()
    return int.from_bytes(h[:8], byteorder="big", signed=True)
