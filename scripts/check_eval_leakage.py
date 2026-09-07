#!/usr/bin/env python3
"""Detect exact and high-overlap prompt leakage between eval datasets."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


def tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return set(re.findall(r"[a-z0-9]+", normalized))


def similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    return len(a & b) / len(a | b) if a | b else 1.0


def load(path: Path) -> list[dict[str, object]]:
    values = [strict_json_loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(value, dict) for value in values):
        raise ValueError("each dataset record must be a JSON object")
    return values


def find_leaks(left: list[dict[str, object]], right: list[dict[str, object]], threshold: float) -> list[dict[str, object]]:
    leaks: list[dict[str, object]] = []
    for a in left:
        for b in right:
            score = similarity(str(a.get("prompt", "")), str(b.get("prompt", "")))
            if score >= threshold:
                leaks.append({"left": a.get("id"), "right": b.get("id"), "similarity": round(score, 6)})
    return leaks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()
    try:
        leaks = find_leaks(load(args.left), load(args.right), args.threshold)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"check_eval_leakage: FAIL ({exc})")
        return 1
    print(json.dumps({"passed": not leaks, "threshold": args.threshold, "leaks": leaks}, indent=2, sort_keys=True))
    return 0 if not leaks else 1


if __name__ == "__main__":
    sys.exit(main())
