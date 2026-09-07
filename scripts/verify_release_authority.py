#!/usr/bin/env python3
"""Standalone external-boundary verifier for signed release authority.

The release workflow executes a protected, hash-pinned copy of this program
from outside the checkout. It deliberately imports no candidate-owned module.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


NAMESPACE = "orchestrate-release"
SSH_KEYGEN = Path("/usr/bin/ssh-keygen")
GIT = Path("/usr/bin/git")
MAX_AGE_SECONDS = 30 * 24 * 60 * 60
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_json(path: Path) -> dict[str, object]:
    def reject_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_pairs)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def regular_file(path: Path) -> Path:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlinked input rejected: {path.name}")
    resolved = absolute.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"regular file required: {path.name}")
    return resolved


def external_file(path: Path, root: Path) -> Path:
    resolved = regular_file(path)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError:
        return resolved
    raise ValueError(f"external authority input is inside checkout: {path.name}")


def allowed_keys(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 4 or fields[1] != f'namespaces="{NAMESPACE}"' or fields[2] != "ssh-ed25519":
            raise ValueError("allowed-signers violates the exact Ed25519 profile")
        principal, key = fields[0], fields[3]
        if not principal or "," in principal or principal in result:
            raise ValueError("allowed-signers contains an invalid or duplicate principal")
        try:
            decoded = base64.b64decode(key, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("allowed-signers contains invalid key data") from exc
        if not decoded:
            raise ValueError("allowed-signers contains empty key data")
        result[principal] = key
    if not result:
        raise ValueError("allowed-signers is empty")
    return result


def issued_at(statement: dict[str, object], now: datetime) -> datetime:
    try:
        issued = datetime.fromisoformat(str(statement["issued_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid issued_at") from exc
    if issued.tzinfo is None:
        raise ValueError("issued_at must be timezone-aware")
    age = (now.astimezone(timezone.utc) - issued.astimezone(timezone.utc)).total_seconds()
    if age < -300 or age > MAX_AGE_SECONDS:
        raise ValueError("signed statement is stale or from the future")
    return issued.astimezone(timezone.utc)


def verify_signature(statement_path: Path, signature_path: Path, allowed: Path, principal: str) -> None:
    verifier = regular_file(SSH_KEYGEN)
    completed = subprocess.run(
        [str(verifier), "-Y", "verify", "-f", str(allowed), "-I", principal, "-n", NAMESPACE, "-s", str(signature_path)],
        input=statement_path.read_bytes(),
        capture_output=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    if completed.returncode != 0:
        raise ValueError(f"OpenSSH signature verification failed for {principal}")


def git_head(root: Path) -> str:
    completed = subprocess.run(
        [str(regular_file(GIT)), "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    head = completed.stdout.strip()
    if completed.returncode != 0 or not HEAD_RE.fullmatch(head):
        raise ValueError("unable to resolve exact Git HEAD")
    return head


def verify(args: argparse.Namespace) -> dict[str, object]:
    root = args.root.resolve(strict=True)
    allowed = external_file(args.allowed_signers, root)
    product_path = external_file(args.product_attestation, root)
    product_signature = external_file(args.product_signature, root)
    final_path = external_file(args.final_attestation, root)
    final_signature = external_file(args.final_signature, root)
    if not SHA256_RE.fullmatch(args.allowed_signers_sha256) or sha256(allowed) != args.allowed_signers_sha256:
        raise ValueError("allowed-signers digest mismatch")
    keys = allowed_keys(allowed)
    principals = [args.product_principal, args.final_principal]
    if any(not principal or principal not in keys for principal in principals):
        raise ValueError("release role principal is absent from allowed-signers")

    product = strict_json(product_path)
    final = strict_json(final_path)
    verify_signature(product_path, product_signature, allowed, args.product_principal)
    verify_signature(final_path, final_signature, allowed, args.final_principal)
    now = datetime.now(timezone.utc)
    product_time = issued_at(product, now)
    final_time = issued_at(final, now)
    if final_time <= product_time:
        raise ValueError("final verifier statement must strictly postdate product approval")

    product_fields = {
        "schema_version", "role", "principal", "issued_at", "head", "skill_sha256",
        "artifact_sha256", "quality_bar_sha256", "budgets_sha256",
        "operational_thresholds_sha256", "external_distribution_approved", "human_labeler_principals",
    }
    final_fields = {
        "schema_version", "role", "principal", "issued_at", "head", "skill_sha256",
        "artifact_sha256", "quality_bar_sha256", "product_attestation_sha256",
        "product_signature_sha256", "verdict",
    }
    if set(product) != product_fields or set(final) != final_fields:
        raise ValueError("signed statement fields are not exact")
    labelers = product.get("human_labeler_principals")
    if not isinstance(labelers, list) or len(labelers) < 2 or any(not isinstance(item, str) or not item for item in labelers):
        raise ValueError("at least two human labeler principals are required")
    all_principals = [args.product_principal, args.final_principal, *labelers]
    if len(all_principals) != len(set(all_principals)) or any(principal not in keys for principal in all_principals):
        raise ValueError("release roles require distinct authorized principals")
    role_keys = [keys[principal] for principal in all_principals]
    if len(role_keys) != len(set(role_keys)):
        raise ValueError("release roles require distinct Ed25519 keys")

    head = git_head(root)
    skill = regular_file(root / "SKILL.md")
    quality_bar = regular_file(root / "config" / "release-quality-bar.json")
    budgets = regular_file(root / "config" / "budgets.json")
    operational = regular_file(root / "config" / "operational-thresholds.json")
    artifact_digest = str(product.get("artifact_sha256", ""))
    if args.artifact is not None:
        artifact_digest = sha256(regular_file(args.artifact))
    elif not SHA256_RE.fullmatch(artifact_digest):
        raise ValueError("preflight artifact digest is malformed")
    product_expected = {
        "schema_version": 1,
        "role": "product-owner",
        "principal": args.product_principal,
        "head": head,
        "skill_sha256": sha256(skill),
        "artifact_sha256": artifact_digest,
        "quality_bar_sha256": sha256(quality_bar),
        "budgets_sha256": sha256(budgets),
        "operational_thresholds_sha256": sha256(operational),
        "external_distribution_approved": True,
    }
    final_expected = {
        "schema_version": 1,
        "role": "independent-verifier",
        "principal": args.final_principal,
        "head": head,
        "skill_sha256": sha256(skill),
        "artifact_sha256": artifact_digest,
        "quality_bar_sha256": sha256(quality_bar),
        "product_attestation_sha256": sha256(product_path),
        "product_signature_sha256": sha256(product_signature),
        "verdict": "APPROVE",
    }
    if any(product.get(key) != value for key, value in product_expected.items()):
        raise ValueError("product statement does not bind the exact candidate")
    if any(final.get(key) != value for key, value in final_expected.items()):
        raise ValueError("final statement does not bind the exact candidate")
    return {
        "passed": True,
        "scope": "preflight" if args.artifact is None else "exact-artifact",
        "head": head,
        "artifact_sha256": artifact_digest,
        "product_principal": args.product_principal,
        "final_principal": args.final_principal,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--allowed-signers", type=Path, required=True)
    parser.add_argument("--allowed-signers-sha256", required=True)
    parser.add_argument("--product-attestation", type=Path, required=True)
    parser.add_argument("--product-signature", type=Path, required=True)
    parser.add_argument("--product-principal", required=True)
    parser.add_argument("--final-attestation", type=Path, required=True)
    parser.add_argument("--final-signature", type=Path, required=True)
    parser.add_argument("--final-principal", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"verify_release_authority: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
