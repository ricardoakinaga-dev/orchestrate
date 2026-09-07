#!/usr/bin/env python3
"""Validate the local chain-of-custody receipt for blind routing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
    from scripts.run_evals import load_jsonl
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads
    from run_evals import load_jsonl


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
THREAD_ID_RE = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]+$")
SEMVER_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")
REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra"}
REQUIRED_SOURCE_FILES = {
    "SKILL.md",
    "references/agent-brief.md",
    "references/delegation.md",
    "references/orchestration-workflow.md",
    "references/recovery.md",
    "references/security.md",
    "references/task-graph.md",
    "references/verification.md",
}
EXPECTED_ALLOWED_INPUTS = {
    "SKILL.md",
    "references/*.md",
    "blind request records containing only id and prompt",
}
ROOT_FIELDS_V1 = {
    "schema_version", "evidence_scope", "release_authority", "immutable", "source_files",
    "dataset", "evaluators", "assignment_constraints", "limitations",
}


def parse_instant(value: object) -> datetime | None:
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant if instant.tzinfo is not None else None


def blind_export_sha256(dataset: Path) -> str:
    cases = load_jsonl(dataset)
    payload = "".join(
        json.dumps({"id": case["id"], "prompt": case["prompt"]}, ensure_ascii=False) + "\n"
        for case in cases
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate(receipt: object, root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt must be a JSON object"]
    version = receipt.get("schema_version")
    expected_root_fields = ROOT_FIELDS_V1 | ({"source_snapshot"} if version == 2 else set())
    if set(receipt) != expected_root_fields:
        errors.append(f"receipt fields must be exactly {sorted(expected_root_fields)}")
    if version not in {1, 2}:
        errors.append("schema_version must equal 1 or 2")
    elif version == 1:
        # Version 1 recorded local claims but no externally verifiable source
        # attestation. Preserve it for audit history; never promote it to current
        # release provenance by merely refreshing hashes and metadata.
        errors.append("schema v1 receipt is historical and cannot establish current source provenance")
    elif receipt.get("immutable") is not True:
        errors.append("schema v2 receipt must declare immutable=true")
    if receipt.get("evidence_scope") != "routing-classification-only":
        errors.append("evidence_scope must be routing-classification-only")
    if receipt.get("release_authority") is not False:
        errors.append("receipt cannot claim release authority")
    if not isinstance(receipt.get("immutable"), bool):
        errors.append("immutable must be boolean")

    source_files = receipt.get("source_files")
    if not isinstance(source_files, list) or not source_files:
        errors.append("source_files must be a non-empty array")
    else:
        declared_sources: set[str] = set()
        for source in source_files:
            if not isinstance(source, dict) or set(source) != {"path", "sha256"}:
                errors.append("each source file needs exactly path and sha256")
                continue
            relative = source.get("path")
            if not isinstance(relative, str):
                errors.append("source path must be text")
                continue
            declared_sources.add(relative)
            path = root / relative
            if not SHA256_RE.fullmatch(str(source.get("sha256", ""))) or not path.is_file() or source.get("sha256") != sha256(path):
                errors.append(f"source hash mismatch: {relative}")
        if declared_sources != REQUIRED_SOURCE_FILES:
            errors.append(f"source_files must be exactly the routed instruction set: {sorted(REQUIRED_SOURCE_FILES)}")

    dataset = receipt.get("dataset")
    if not isinstance(dataset, dict) or set(dataset) != {"path", "sha256", "blind_export_sha256"}:
        errors.append("dataset needs exactly path, sha256, and blind_export_sha256")
    else:
        relative = dataset.get("path")
        if relative != "evals/cases.jsonl" or not (root / str(relative)).is_file():
            errors.append("dataset path is missing")
        else:
            path = root / relative
            if not SHA256_RE.fullmatch(str(dataset.get("sha256", ""))) or dataset.get("sha256") != sha256(path):
                errors.append("dataset hash mismatch")
            if not SHA256_RE.fullmatch(str(dataset.get("blind_export_sha256", ""))) or dataset.get("blind_export_sha256") != blind_export_sha256(path):
                errors.append("blind export hash mismatch")

    snapshot_digest: str | None = None
    snapshot_captured_at: datetime | None = None
    if version == 2:
        snapshot = receipt.get("source_snapshot")
        if not isinstance(snapshot, dict) or set(snapshot) != {"path", "sha256"}:
            errors.append("source_snapshot needs exactly path and sha256")
        else:
            snapshot_relative = snapshot.get("path")
            expected_snapshot_path = "evals/evidence/routing-v3/source-snapshot.json"
            snapshot_path = root / str(snapshot_relative)
            if (
                snapshot_relative != expected_snapshot_path
                or snapshot_path.is_symlink()
                or not snapshot_path.is_file()
                or not SHA256_RE.fullmatch(str(snapshot.get("sha256", "")))
                or snapshot.get("sha256") != sha256(snapshot_path)
            ):
                errors.append("source_snapshot path or hash mismatch")
            else:
                snapshot_digest = str(snapshot["sha256"])
                try:
                    snapshot_data = strict_json_loads(snapshot_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    snapshot_data = None
                expected_snapshot = {
                    "schema_version": 1,
                    "captured_at": snapshot_data.get("captured_at") if isinstance(snapshot_data, dict) else None,
                    "source_files": source_files,
                    "dataset": dataset,
                    "assignment_constraints": receipt.get("assignment_constraints"),
                }
                if snapshot_data != expected_snapshot:
                    errors.append("source_snapshot does not freeze the receipt inputs and constraints")
                else:
                    snapshot_captured_at = parse_instant(snapshot_data.get("captured_at"))
                    if snapshot_captured_at is None:
                        errors.append("source_snapshot captured_at must be an ISO-8601 instant")

    evaluators = receipt.get("evaluators")
    if not isinstance(evaluators, list) or len(evaluators) != 3:
        errors.append("exactly three evaluator receipts are required")
        evaluators = []
    thread_ids: set[str] = set()
    agent_paths: set[str] = set()
    run_numbers: set[int] = set()
    for evaluator in evaluators:
        required = {
            "run", "thread_id", "agent_path", "agent_nickname", "model", "reasoning_effort",
            "cli_version", "started_at", "completed_at", "tokens_used", "output",
        }
        if version == 2:
            required.update({"source_snapshot_sha256", "session_rollout", "prompt", "invocation"})
        else:
            required.add("session_rollout_sha256")
        if not isinstance(evaluator, dict) or set(evaluator) != required:
            errors.append("each evaluator receipt has an invalid field set")
            continue
        run = evaluator.get("run")
        thread_id = evaluator.get("thread_id")
        agent_path = evaluator.get("agent_path")
        if not isinstance(run, int) or run not in {1, 2, 3}:
            errors.append("evaluator run must be 1, 2, or 3")
        else:
            run_numbers.add(run)
        if not isinstance(thread_id, str) or not THREAD_ID_RE.fullmatch(thread_id):
            errors.append("evaluator thread_id must use the recorded UUID form")
        else:
            thread_ids.add(thread_id)
        if not isinstance(agent_path, str) or not agent_path:
            errors.append("evaluator agent_path is required")
        else:
            agent_paths.add(agent_path)
        if not isinstance(evaluator.get("agent_nickname"), str) or not evaluator.get("agent_nickname"):
            errors.append(f"run {run}: agent_nickname is required")
        if not MODEL_RE.fullmatch(str(evaluator.get("model", ""))):
            errors.append(f"run {run}: model has invalid format")
        if evaluator.get("reasoning_effort") not in REASONING_EFFORTS:
            errors.append(f"run {run}: reasoning_effort is invalid")
        if not SEMVER_RE.fullmatch(str(evaluator.get("cli_version", ""))):
            errors.append(f"run {run}: cli_version must be semantic version text")
        started = parse_instant(evaluator.get("started_at"))
        completed = parse_instant(evaluator.get("completed_at"))
        if started is None or completed is None or completed <= started:
            errors.append(f"run {run}: timestamps must be ordered ISO-8601 instants")
        elif version == 2 and (snapshot_captured_at is None or started < snapshot_captured_at):
            errors.append(f"run {run}: evaluation started before the frozen source snapshot")
        if version == 2 and evaluator.get("source_snapshot_sha256") != snapshot_digest:
            errors.append(f"run {run}: evaluator is not bound to the source snapshot")
        if version == 1 and not SHA256_RE.fullmatch(str(evaluator.get("session_rollout_sha256", ""))):
            errors.append(f"run {run}: session_rollout_sha256 must be a SHA-256 digest")
        if version == 2:
            for field, filename in (
                ("session_rollout", f"session-{run}.jsonl"),
                ("prompt", f"prompt-{run}.txt"),
                ("invocation", f"invocation-{run}.json"),
            ):
                descriptor = evaluator.get(field)
                expected_path = f"evals/evidence/routing-v3/{filename}"
                if not isinstance(descriptor, dict) or set(descriptor) != {"path", "sha256"}:
                    errors.append(f"run {run}: {field} needs exactly path and sha256")
                    continue
                relative = descriptor.get("path")
                path = root / str(relative)
                if (
                    relative != expected_path
                    or path.is_symlink()
                    or not path.is_file()
                    or not SHA256_RE.fullmatch(str(descriptor.get("sha256", "")))
                    or descriptor.get("sha256") != sha256(path)
                ):
                    errors.append(f"run {run}: {field} path or hash mismatch")
        if not isinstance(evaluator.get("tokens_used"), int) or evaluator.get("tokens_used", 0) <= 0:
            errors.append(f"run {run}: tokens_used must be positive")
        output = evaluator.get("output")
        if not isinstance(output, dict) or set(output) != {"path", "sha256"}:
            errors.append(f"run {run}: output needs exactly path and sha256")
        else:
            relative = output.get("path")
            evidence_version = "routing-v3" if version == 2 else "routing-v2"
            expected_path = f"evals/evidence/{evidence_version}/run-{run}.jsonl"
            if relative != expected_path or not (root / str(relative)).is_file() or not SHA256_RE.fullmatch(str(output.get("sha256", ""))) or output.get("sha256") != sha256(root / str(relative)):
                errors.append(f"run {run}: output hash mismatch")
            elif isinstance(run, int):
                records = load_jsonl(root / relative)
                if any(record.get("run") != run for record in records):
                    errors.append(f"run {run}: output contains another run number")
    if run_numbers != {1, 2, 3}:
        errors.append("evaluator runs must be unique and complete")
    if len(thread_ids) != 3 or len(agent_paths) != 3:
        errors.append("evaluator thread IDs and agent paths must be distinct")

    constraints = receipt.get("assignment_constraints")
    expected_constraint_keys = {"allowed_inputs", "gold_labels_denied", "prior_evidence_denied", "output_contract"}
    if not isinstance(constraints, dict) or set(constraints) != expected_constraint_keys:
        errors.append("assignment constraints have an invalid field set")
    elif (
        not isinstance(constraints.get("allowed_inputs"), list)
        or set(constraints["allowed_inputs"]) != EXPECTED_ALLOWED_INPUTS
        or constraints.get("gold_labels_denied") is not True
        or constraints.get("prior_evidence_denied") is not True
        or constraints.get("output_contract") != "one routing prediction per case with fixed run number"
    ):
        errors.append("assignment constraints contradict the frozen blind-evaluation contract")
    limitations = receipt.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(isinstance(item, str) and item for item in limitations):
        errors.append("limitations must be a non-empty string array")
    else:
        normalized_limitations = " ".join(limitations).casefold()
        required_disclosures = ["does not independently prove", "does not prove installed runtime behavior"]
        if receipt.get("immutable") is False:
            required_disclosures.append("not immutable")
        elif "not immutable" in normalized_limitations:
            errors.append("immutable=true contradicts a not-immutable limitation")
        for required in required_disclosures:
            if required not in normalized_limitations:
                errors.append(f"limitations must disclose: {required}")
    return errors


def validate_expected_stale(receipt: object, root: Path) -> tuple[list[str], list[str]]:
    """Accept a historical receipt only when source drift is its sole defect.

    This keeps old blind evidence auditable without relabeling it as current. Dataset,
    output, evaluator, blinding-contract, and limitation defects remain failures.
    """
    errors = validate(receipt, root)
    historical = "schema v1 receipt is historical and cannot establish current source provenance"
    source_drift = sorted(error for error in errors if error.startswith("source hash mismatch: "))
    blocking = [error for error in errors if error not in source_drift and error != historical]
    if not source_drift:
        blocking.append("expected historical source drift, but the receipt is current")
    if not isinstance(receipt, dict) or receipt.get("immutable") is not False:
        blocking.append("an expected-stale receipt must declare immutable=false")
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
        blocking.append("expected-stale mode is restricted to historical schema v1 receipts")
    return blocking, source_drift


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path, nargs="?", default=root / "evals" / "evidence" / "routing-v2" / "receipt.json")
    parser.add_argument(
        "--expect-stale-sources",
        action="store_true",
        help="pass only when source-hash drift is the sole defect; never marks the receipt current",
    )
    args = parser.parse_args()
    try:
        receipt = strict_json_loads(args.receipt.read_text(encoding="utf-8"))
        if args.expect_stale_sources:
            errors, source_drift = validate_expected_stale(receipt, root)
        else:
            errors = validate(receipt, root)
            source_drift = []
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        errors = [str(exc)]
        source_drift = []
    for error in errors:
        print(f"ERROR {error}")
    if args.expect_stale_sources and not errors:
        print(f"validate_routing_receipt: STALE AS EXPECTED ({len(source_drift)} changed source files; 0 blocking errors)")
    else:
        print(f"validate_routing_receipt: {'PASS' if not errors else 'FAIL'} ({len(errors)} errors)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
