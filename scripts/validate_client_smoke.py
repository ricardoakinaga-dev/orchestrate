#!/usr/bin/env python3
"""Validate a client-smoke result without converting missing checks into support."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


CLIENTS = {"codex-cli", "codex-ide", "chatgpt-desktop", "local-plugin-harness"}
CHECK_NAMES = {"installation", "discovery", "explicit-invocation", "implicit-routing", "recovery"}
STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT RUN"}
SUPPORT_STATUSES = {"SUPPORTED", "EXPERIMENTAL", "UNSUPPORTED"}
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_symlink_component(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def validate(data: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["result must be a JSON object"]
    required = {"schema_version", "client", "client_version", "artifact_sha256", "environment", "checks", "support_status"}
    if set(data) != required:
        errors.append(f"root fields must be exactly {sorted(required)}")
    if data.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if data.get("client") not in CLIENTS:
        errors.append("client is invalid")
    version = data.get("client_version")
    if version is not None and (not isinstance(version, str) or not version.strip()):
        errors.append("client_version must be null or non-empty text")
    if not isinstance(data.get("artifact_sha256"), str) or not SHA256_RE.fullmatch(str(data.get("artifact_sha256", ""))):
        errors.append("artifact_sha256 must be a lowercase SHA-256")
    if not isinstance(data.get("environment"), str) or not str(data.get("environment", "")).strip():
        errors.append("environment is required")
    support_status = data.get("support_status")
    if support_status not in SUPPORT_STATUSES:
        errors.append("support_status is invalid")

    checks = data.get("checks")
    seen: set[str] = set()
    statuses: list[str] = []
    if not isinstance(checks, list):
        errors.append("checks must be an array")
    else:
        required_check = {"name", "status", "procedure", "summary", "artifact"}
        for index, check in enumerate(checks, start=1):
            if not isinstance(check, dict) or set(check) != required_check:
                errors.append(f"check {index} fields must be exactly {sorted(required_check)}")
                continue
            name = check.get("name")
            status = check.get("status")
            if name not in CHECK_NAMES:
                errors.append(f"check {index} has invalid name")
            elif str(name) in seen:
                errors.append(f"duplicate check {name}")
            else:
                seen.add(str(name))
            if status not in STATUSES:
                errors.append(f"check {index} has invalid status")
            else:
                statuses.append(str(status))
            if not all(isinstance(check.get(field), str) and str(check[field]).strip() for field in ("procedure", "summary")):
                errors.append(f"check {index} needs procedure and summary")
            artifact = check.get("artifact")
            if artifact is not None and (
                not isinstance(artifact, dict)
                or set(artifact) != {"path", "sha256"}
                or not isinstance(artifact.get("path"), str)
                or not artifact["path"].strip()
                or not isinstance(artifact.get("sha256"), str)
                or not SHA256_RE.fullmatch(artifact["sha256"])
            ):
                errors.append(f"check {index} artifact must be null or an exact path/sha256 object")
        if seen != CHECK_NAMES:
            errors.append(f"checks must cover exactly {sorted(CHECK_NAMES)}")

    all_pass = len(statuses) == len(CHECK_NAMES) and all(status == "PASS" for status in statuses)
    complete_artifacts = isinstance(checks, list) and all(
        isinstance(check, dict) and isinstance(check.get("artifact"), dict) for check in checks
    )
    if support_status == "SUPPORTED" and (not all_pass or version is None or not complete_artifacts):
        errors.append("SUPPORTED requires a version, PASS, and bound evidence artifact for every required check")
    if support_status == "UNSUPPORTED" and all_pass:
        errors.append("UNSUPPORTED contradicts five passing checks; use SUPPORTED or document another failure")
    return errors


def validate_artifacts(data: object, root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict) or not isinstance(data.get("checks"), list):
        return ["cannot verify artifacts for an invalid report shape"]
    root = root.resolve()
    seen: set[str] = set()
    for check in data["checks"]:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name", "unknown"))
        artifact = check.get("artifact")
        if not isinstance(artifact, dict):
            if data.get("support_status") == "SUPPORTED":
                errors.append(f"{name} lacks a bound artifact")
            continue
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or relative in seen:
            errors.append(f"{name} artifact path is invalid or duplicated")
            continue
        seen.add(relative)
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            errors.append(f"{name} artifact is missing or escapes the root")
            continue
        if has_symlink_component(candidate, root) or not resolved.is_file():
            errors.append(f"{name} artifact is not a regular non-symlink file")
        elif expected != sha256(resolved):
            errors.append(f"{name} artifact SHA-256 mismatch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--verify-artifacts", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        data = strict_json_loads(args.result.read_text(encoding="utf-8"))
        errors = validate(data)
        if args.verify_artifacts:
            errors.extend(validate_artifacts(data, args.root))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"validate_client_smoke: FAIL ({exc})")
        return 1
    for error in errors:
        print(f"ERROR {error}")
    print(f"validate_client_smoke: {'PASS' if not errors else 'FAIL'} ({len(errors)} errors)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
