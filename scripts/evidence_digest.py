#!/usr/bin/env python3
"""Create a bounded, redacted evidence digest from a local log artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(authorization\s*:\s*bearer|password|passwd|token|secret|api[_-]?key|client[_-]?secret)\s*[:=]\s*[^\s,;]+"),
)


def sanitize(text: str) -> str:
    for pattern in PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def create_digest(path: Path, sanitized_output: Path, check: str, exit_code: int, max_chars: int = 800) -> dict[str, object]:
    if path.resolve() == sanitized_output.resolve():
        raise ValueError("sanitized output must not overwrite the raw log")
    if sanitized_output.exists() or sanitized_output.is_symlink():
        raise ValueError("sanitized output already exists")
    raw = path.read_text(encoding="utf-8", errors="replace")
    cleaned = sanitize(raw)
    sanitized_output.parent.mkdir(parents=True, exist_ok=True)
    sanitized_output.write_text(cleaned, encoding="utf-8")
    excerpt = cleaned[:max_chars]
    truncated = len(cleaned) > max_chars
    return {
        "check": check,
        "exit_code": exit_code,
        "result": "PASS" if exit_code == 0 else "FAIL",
        "summary": f"{len(raw)} characters captured; sanitized excerpt {'truncated' if truncated else 'complete'}.",
        "excerpt": excerpt,
        "truncated": truncated,
        "artifact": str(sanitized_output),
        "integrity": "sha256:" + hashlib.sha256(sanitized_output.read_bytes()).hexdigest(),
        "artifact_sanitized": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--sanitized-output", type=Path, required=True)
    parser.add_argument("--check", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--max-chars", type=int, default=800)
    args = parser.parse_args()
    try:
        if not 100 <= args.max_chars <= 4000:
            raise ValueError("max-chars must be between 100 and 4000")
        print(json.dumps(create_digest(args.log, args.sanitized_output, args.check, args.exit_code, args.max_chars), indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"evidence_digest: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
