from __future__ import annotations

import re


_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def normalize_entity_id(value: str) -> str:
    value = value.strip().lower().replace("-", "_")
    value = _SLUG_RE.sub("_", value)
    return value.strip("_")
