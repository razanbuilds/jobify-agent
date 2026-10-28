"""Capped persistent memory: user preferences stored in data/memory.json, injected into the system prompt."""
from __future__ import annotations

import json

from . import config


def load_memory_text(cap: int = 1500) -> str:
    p = config.DATA_DIR / "memory.json"
    if not p.exists():
        return "(no saved preferences)"
    data = json.loads(p.read_text(encoding="utf-8"))
    lines = []
    for k, v in data.items():
        v = ", ".join(map(str, v)) if isinstance(v, list) else v
        lines.append(f"- {k}: {v}")
    text = "\n".join(lines)
    return text[:cap]  # hard cap: memory must never eat the context budget
