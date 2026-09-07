#!/usr/bin/env python3
"""Recompute a stored Codex CLI probe bundle from its raw JSONL evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
    from scripts.run_codex_runtime_probe import (
        CANARY,
        charged_tokens,
        derive_trace,
        extract_install,
        inspect_events,
        prompt,
        sha256,
        snapshot,
        validate_result,
    )
    from scripts.validate_client_smoke import validate as validate_client_smoke
    from scripts.validate_client_smoke import validate_artifacts
    from scripts.validate_runtime_safety import summarize as summarize_runtime_safety
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads
    from run_codex_runtime_probe import CANARY, charged_tokens, derive_trace, extract_install, inspect_events, prompt, sha256, snapshot, validate_result
    from validate_client_smoke import validate as validate_client_smoke
    from validate_client_smoke import validate_artifacts
    from validate_runtime_safety import summarize as summarize_runtime_safety


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_FIELDS = {
    "schema_version",
    "activation",
    "artifact_sha256",
    "charged_tokens",
    "client",
    "client_version",
    "exit_code",
    "prompt",
    "prompt_sha256",
    "raw_jsonl",
    "raw_jsonl_sha256",
    "result",
    "skill_sha256",
    "stderr",
    "stderr_sha256",
    "usage",
    "workspace_post_sha256",
    "workspace_pre_sha256",
}
SAFE_STDERR = {"", "Reading additional input from stdin...\n"}


def load_json(path: Path) -> dict[str, object]:
    if path.is_symlink():
        raise ValueError(f"refusing symlink JSON: {path}")
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def bound_file(root: Path, relative: object, expected: object | None = None) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("evidence path must be non-empty and repository-relative")
    root = root.resolve()
    candidate = root / relative
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"evidence path contains a symlink: {relative}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"evidence path escapes the repository: {relative}") from exc
    if not resolved.is_file():
        raise ValueError(f"evidence path is not a regular file: {relative}")
    if expected is not None and (not isinstance(expected, str) or not SHA256_RE.fullmatch(expected) or sha256(resolved) != expected):
        raise ValueError(f"evidence SHA-256 mismatch: {relative}")
    return resolved


def load_trace(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = strict_json_loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"trace line {number} is not an object")
        events.append(value)
    return events


def verify_probe_bundle(root: Path, artifact: Path) -> dict[str, object]:
    root = root.resolve(strict=True)
    artifact = artifact.absolute()
    current = Path(artifact.anchor)
    for part in artifact.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError("artifact path contains a symlink")
    artifact = artifact.resolve(strict=True)
    if not artifact.is_file():
        raise ValueError("artifact must be a regular non-symlink file")
    artifact_digest = sha256(artifact)
    skill_digest = sha256(root / "SKILL.md")
    client_report_path = root / "evals" / "reports" / "client-smoke-codex-cli.json"
    client_report = load_json(client_report_path)
    errors = [*validate_client_smoke(client_report), *validate_artifacts(client_report, root)]
    if errors:
        raise ValueError("client report failed validation: " + "; ".join(errors))
    version = client_report.get("client_version")
    if (
        client_report.get("client") != "codex-cli"
        or client_report.get("support_status") != "SUPPORTED"
        or not isinstance(version, str)
        or not version
        or client_report.get("artifact_sha256") != artifact_digest
    ):
        raise ValueError("client report identity is not bound to the exact artifact")
    budget = load_json(root / "config" / "budgets.json")
    classes = budget.get("classes")
    direct = classes.get("direct") if isinstance(classes, dict) else None
    max_tokens = direct.get("max_tokens") if isinstance(direct, dict) else None
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
        raise ValueError("direct token budget is invalid")
    with tempfile.TemporaryDirectory(prefix="orchestrate-probe-recompute-") as temporary:
        expected_workspace = Path(temporary) / "work"
        expected_workspace.mkdir()
        extract_install(artifact, expected_workspace, root)
        expected_workspace_digest, _ = snapshot(expected_workspace)

    evidence_relative = f"evals/evidence/client-smoke-codex-cli-{version}"
    evidence_dir = root / evidence_relative
    results: dict[str, dict[str, object]] = {}
    receipts: dict[str, dict[str, object]] = {}
    evidence_paths: set[str] = {
        "evals/reports/client-smoke-codex-cli.json",
        "evals/reports/runtime-safety-v2.json",
        "evals/evidence/runtime-safety-v2/trace.jsonl",
    }
    for activation in ("explicit", "implicit"):
        receipt_relative = f"{evidence_relative}/{activation}-invocation.json"
        receipt = load_json(root / receipt_relative)
        receipts[activation] = receipt
        if set(receipt) != RECEIPT_FIELDS or receipt.get("schema_version") != 1:
            raise ValueError(f"{activation} receipt has invalid fields or schema")
        if (
            receipt.get("activation") != activation
            or receipt.get("artifact_sha256") != artifact_digest
            or receipt.get("client") != "codex-cli"
            or receipt.get("client_version") != version
            or receipt.get("exit_code") != 0
            or receipt.get("skill_sha256") != skill_digest
        ):
            raise ValueError(f"{activation} receipt identity mismatch")
        expected_raw = f"{evidence_relative}/{activation}.jsonl"
        expected_stderr = f"{evidence_relative}/{activation}.stderr.txt"
        expected_prompt = f"{evidence_relative}/{activation}.prompt.txt"
        if receipt.get("raw_jsonl") != expected_raw or receipt.get("stderr") != expected_stderr or receipt.get("prompt") != expected_prompt:
            raise ValueError(f"{activation} receipt references unexpected evidence paths")
        raw = bound_file(root, receipt["raw_jsonl"], receipt.get("raw_jsonl_sha256"))
        stderr = bound_file(root, receipt["stderr"], receipt.get("stderr_sha256"))
        prompt_path = bound_file(root, receipt["prompt"], receipt.get("prompt_sha256"))
        if prompt_path.read_text(encoding="utf-8") != prompt(root, activation):
            raise ValueError(f"{activation} prompt differs from current scenario sources")
        stderr_text = stderr.read_text(encoding="utf-8")
        if stderr_text not in SAFE_STDERR or CANARY in stderr_text:
            raise ValueError(f"{activation} stderr contains unexpected content")
        events: list[dict[str, object]] = []
        for number, line in enumerate(raw.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = strict_json_loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{activation} JSONL line {number} is not an object")
            events.append(value)
        result, commands, usage = inspect_events(events, CANARY)
        reported_result = receipt.get("result")
        if result != reported_result or not isinstance(result, dict):
            raise ValueError(f"{activation} receipt does not reproduce from raw JSONL")
        skill = result.get("skill")
        if not isinstance(skill, dict) or not isinstance(skill.get("path"), str):
            raise ValueError(f"{activation} result lacks a skill path")
        validate_result(result, activation, Path(skill["path"]), skill_digest, commands)
        if receipt.get("usage") != usage or receipt.get("charged_tokens") != charged_tokens(usage):
            raise ValueError(f"{activation} usage does not reproduce from raw JSONL")
        if charged_tokens(usage) > max_tokens:
            raise ValueError(f"{activation} probe exceeds the direct token budget")
        pre = receipt.get("workspace_pre_sha256")
        post = receipt.get("workspace_post_sha256")
        if (
            not isinstance(pre, str)
            or not SHA256_RE.fullmatch(pre)
            or pre != post
            or pre != expected_workspace_digest
        ):
            raise ValueError(f"{activation} workspace mutation sentinel is invalid")
        results[activation] = result
        evidence_paths.update({receipt_relative, expected_raw, expected_stderr, expected_prompt})

    installation_relative = f"{evidence_relative}/installation.json"
    discovery_relative = f"{evidence_relative}/discovery.json"
    recovery_relative = f"{evidence_relative}/recovery.json"
    installation = load_json(root / installation_relative)
    discovery = load_json(root / discovery_relative)
    recovery = load_json(root / recovery_relative)
    evidence_paths.update({installation_relative, discovery_relative, recovery_relative})
    expected_installation = {
        "schema_version": 1,
        "artifact_sha256": artifact_digest,
        "client": "codex-cli",
        "client_version": version,
        "installation_scope": "isolated-repository-.agents/skills",
        "skill_sha256": skill_digest,
        "explicit_workspace_sha256": receipts["explicit"]["workspace_pre_sha256"],
        "implicit_workspace_sha256": receipts["implicit"]["workspace_pre_sha256"],
        "explicit_charged_tokens": receipts["explicit"]["charged_tokens"],
        "implicit_charged_tokens": receipts["implicit"]["charged_tokens"],
        "passed": True,
    }
    if installation != expected_installation:
        raise ValueError("installation receipt does not reproduce")
    expected_discovery = {
        "schema_version": 1,
        "client": "codex-cli",
        "client_version": version,
        "explicit_skill": results["explicit"]["skill"],
        "implicit_skill": results["implicit"]["skill"],
        "explicit_log_sha256": receipts["explicit"]["raw_jsonl_sha256"],
        "implicit_log_sha256": receipts["implicit"]["raw_jsonl_sha256"],
        "passed": True,
    }
    if discovery != expected_discovery:
        raise ValueError("discovery receipt does not reproduce")
    expected_recovery = {
        "schema_version": 1,
        "explicit": results["explicit"]["recovery"],
        "implicit": results["implicit"]["recovery"],
        "state_preserved": True,
        "passed": True,
    }
    if recovery != expected_recovery:
        raise ValueError("recovery receipt does not reproduce")

    expected_artifacts = {
        "installation": installation_relative,
        "discovery": discovery_relative,
        "explicit-invocation": f"{evidence_relative}/explicit-invocation.json",
        "implicit-routing": f"{evidence_relative}/implicit-invocation.json",
        "recovery": recovery_relative,
    }
    checks = client_report.get("checks")
    if not isinstance(checks, list) or {
        str(item.get("name")): item.get("artifact", {}).get("path")
        for item in checks
        if isinstance(item, dict) and isinstance(item.get("artifact"), dict)
    } != expected_artifacts:
        raise ValueError("client report check artifacts do not match the exact probe bundle")

    trace_relative = "evals/evidence/runtime-safety-v2/trace.jsonl"
    trace_path = bound_file(root, trace_relative)
    expected_trace = derive_trace(results)
    if load_trace(trace_path) != expected_trace:
        raise ValueError("runtime action trace does not reproduce from raw Codex results")
    runtime_relative = "evals/reports/runtime-safety-v2.json"
    runtime_path = bound_file(root, runtime_relative)
    runtime = load_json(runtime_path)
    observer = (
        "scripts/run_codex_runtime_probe.py verified Codex JSONL tool events, exact installed Skill identity, "
        "synthetic-secret non-disclosure, packaged-validator rejection, and byte-identical pre/post read-only workspaces; "
        f"explicit_jsonl_sha256={receipts['explicit']['raw_jsonl_sha256']};"
        f"implicit_jsonl_sha256={receipts['implicit']['raw_jsonl_sha256']}"
    )
    recomputed_runtime = summarize_runtime_safety(
        root,
        trace_path,
        artifact,
        "codex-cli",
        version,
        "codex-exec-jsonl",
        "Linux x86_64; isolated repository skill; --ephemeral --ignore-user-config --ignore-rules --sandbox read-only; shell environment inheritance none",
        observer,
    )
    if runtime != recomputed_runtime or runtime.get("passed") is not True:
        raise ValueError("runtime report does not reproduce from raw Codex evidence")
    return {
        "passed": True,
        "artifact_sha256": artifact_digest,
        "skill_sha256": skill_digest,
        "client": "codex-cli",
        "client_version": version,
        "explicit_charged_tokens": receipts["explicit"]["charged_tokens"],
        "implicit_charged_tokens": receipts["implicit"]["charged_tokens"],
        "trace_events": len(expected_trace),
        "evidence_paths": sorted(evidence_paths),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_probe_bundle(root, args.artifact)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"verify_codex_runtime_probe: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
