#!/usr/bin/env python3
"""Strict JSON parsing that rejects duplicate object keys."""

from __future__ import annotations

import json
from typing import Any


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_object)
