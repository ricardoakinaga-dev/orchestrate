#!/usr/bin/env python3
"""Verify externally anchored OpenSSH signatures over strict JSON statements."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


NAMESPACE = "orchestrate-release"
MAX_ATTESTATION_AGE_SECONDS = 30 * 24 * 60 * 60
SSH_KEYGEN = Path("/usr/bin/ssh-keygen")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular_file_without_symlink(path: Path) -> Path | None:
    """Resolve a regular file only when no path component is a symlink."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current = current / part
            if current.is_symlink():
                return None
        resolved = absolute.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_file() else None


def allowed_signer_keys(path: Path) -> dict[str, str] | None:
    """Parse the deliberately narrow trust-anchor profile used by releases."""
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not lines:
        return None
    for line in lines:
        fields = line.split()
        if len(fields) != 4 or fields[1] != f'namespaces="{NAMESPACE}"' or fields[2] != "ssh-ed25519":
            return None
        principal, key = fields[0], fields[3]
        if not principal or "," in principal or principal in result:
            return None
        try:
            decoded = base64.b64decode(key, validate=True)
        except (binascii.Error, ValueError):
            return None
        if not decoded:
            return None
        result[principal] = key
    return result


def principals_have_distinct_keys(path: Path, principals: list[str]) -> bool:
    keys = allowed_signer_keys(path)
    if keys is None or len(principals) != len(set(principals)):
        return False
    selected = [keys.get(principal) for principal in principals]
    return all(selected) and len(selected) == len(set(selected))


def external_evidence_file(root: Path, environment: dict[str, str], variable: str) -> Path | None:
    """Resolve a protected release input that must live outside the repository."""
    value = environment.get(variable, "")
    if not value:
        return None
    resolved = regular_file_without_symlink(Path(value))
    if resolved is None:
        return None
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError:
        return resolved
    except OSError:
        return None
    return None


def external_trust_anchor(root: Path, environment: dict[str, str]) -> Path | None:
    """Resolve a protected, out-of-repository allowed-signers file."""
    value = environment.get("ORCHESTRATE_ALLOWED_SIGNERS", "")
    expected_digest = environment.get("ORCHESTRATE_ALLOWED_SIGNERS_SHA256", "")
    if not value or len(expected_digest) != 64:
        return None
    anchor = external_evidence_file(root, environment, "ORCHESTRATE_ALLOWED_SIGNERS")
    if anchor is None or sha256(anchor) != expected_digest or allowed_signer_keys(anchor) is None:
        return None
    return anchor


def load_signed_statement(
    statement_path: Path,
    signature_path: Path,
    allowed_signers: Path,
    principal: str,
    *,
    now: datetime | None = None,
) -> dict[str, object] | None:
    statement_path = regular_file_without_symlink(statement_path) or Path()
    signature_path = regular_file_without_symlink(signature_path) or Path()
    allowed_signers = regular_file_without_symlink(allowed_signers) or Path()
    keys = allowed_signer_keys(allowed_signers)
    if not principal or keys is None or principal not in keys or not statement_path.is_file() or not signature_path.is_file() or not allowed_signers.is_file():
        return None
    try:
        payload = statement_path.read_bytes()
        statement = strict_json_loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(statement, dict) or statement.get("principal") != principal:
        return None
    try:
        issued_at = datetime.fromisoformat(str(statement.get("issued_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return None
    current = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None or current.tzinfo is None:
        return None
    age = (current.astimezone(timezone.utc) - issued_at.astimezone(timezone.utc)).total_seconds()
    if age < -300 or age > MAX_ATTESTATION_AGE_SECONDS:
        return None
    verifier = regular_file_without_symlink(SSH_KEYGEN)
    if verifier is None:
        return None
    try:
        completed = subprocess.run(
            [
                str(verifier), "-Y", "verify", "-f", str(allowed_signers), "-I", principal,
                "-n", NAMESPACE, "-s", str(signature_path),
            ],
            input=payload,
            capture_output=True,
            check=False,
            env={"PATH": "/usr/bin:/bin"},
        )
    except OSError:
        return None
    return statement if completed.returncode == 0 else None
