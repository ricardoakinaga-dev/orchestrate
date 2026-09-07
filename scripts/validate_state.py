#!/usr/bin/env python3
"""Validate an Orchestrate task ledger, contracts, evidence, and ownership."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


STATUSES = {"PENDING", "READY", "RUNNING", "IMPLEMENTED", "REVIEW", "REWORK", "VERIFIED", "DONE", "BLOCKED", "FAILED"}
ACTIVE = {"RUNNING"}
SATISFIED_DEPENDENCY = {"VERIFIED", "DONE"}
TRANSITIONS = {
    "PENDING": {"READY", "BLOCKED", "FAILED"},
    "READY": {"RUNNING", "BLOCKED", "FAILED"},
    "RUNNING": {"IMPLEMENTED", "BLOCKED", "FAILED"},
    "IMPLEMENTED": {"REVIEW", "BLOCKED", "FAILED"},
    "REVIEW": {"VERIFIED", "REWORK", "BLOCKED", "FAILED"},
    "REWORK": {"RUNNING", "BLOCKED", "FAILED"},
    "VERIFIED": {"DONE", "REWORK"},
    "DONE": {"REVIEW", "REWORK"},
    "BLOCKED": {"READY", "FAILED"},
    "FAILED": set(),
}
ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]*$")
GLOB_META = set("*?[")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TOP_LEVEL_FIELDS = {"schema_version", "goal", "contracts", "limits", "evidence_registry", "tasks"}
TASK_FIELDS = {"id", "status", "dependencies", "owns", "contracts", "criteria", "attempts", "history", "open_findings"}
EXECUTION_FIELDS = {
    "process_id",
    "process_start_token",
    "observed_at",
    "checkpoint_generation",
    "workspace_fingerprint",
    "artifact_fingerprint",
    "observer",
}


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    task: str | None = None


def resource_base(resource: str) -> tuple[str, str]:
    normalized = resource.strip().replace("\\", "/")
    if ":" in normalized and not normalized.startswith(("./", "../")):
        kind, value = normalized.split(":", 1)
        if kind != "path":
            return kind, value.strip().rstrip("/*")
        normalized = value
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    prefix = "/" if normalized.startswith("/") else ""
    return "path", (prefix + "/".join(parts)).rstrip("/*")


def fixed_glob_prefix(resource: str) -> str:
    parts: list[str] = []
    _, normalized = resource_base(resource)
    for part in PurePosixPath(normalized).parts:
        if any(char in part for char in GLOB_META):
            break
        parts.append(part)
    return "/".join(parts).rstrip("/")


def overlaps(left: str, right: str) -> bool:
    left_kind, left_value = resource_base(left)
    right_kind, right_value = resource_base(right)
    if left_kind != right_kind:
        return False
    if left_kind != "path":
        return left_value == right_value
    left_glob = any(char in left_value for char in GLOB_META)
    right_glob = any(char in right_value for char in GLOB_META)
    if left_glob or right_glob:
        left_prefix = fixed_glob_prefix(left_value)
        right_prefix = fixed_glob_prefix(right_value)
        if not left_prefix or not right_prefix:
            return True
        return (
            left_prefix == right_prefix
            or left_prefix.startswith(right_prefix + "/")
            or right_prefix.startswith(left_prefix + "/")
        )
    return left_value == right_value or left_value.startswith(right_value + "/") or right_value.startswith(left_value + "/")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contracts_integrity(contracts: dict[str, str]) -> str:
    canonical = json.dumps(contracts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def local_artifact_issue(artifact: object, integrity: object, root: Path, label: str) -> tuple[str, str] | None:
    if not isinstance(artifact, str) or not artifact.strip():
        return "EVIDENCE_ARTIFACT", f"{label} needs a non-empty local artifact reference"
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", artifact) or artifact.startswith("//"):
        return "EVIDENCE_UNVERIFIABLE", f"{label} must be materialized as a local, hash-verified artifact"
    unresolved = root / artifact
    current = root
    for part in Path(artifact).parts:
        current = current / part
        if current.is_symlink():
            return "EVIDENCE_SYMLINK", f"{label} must not be reached through a symlink: {artifact!r}"
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return "EVIDENCE_ESCAPE", f"{label} escapes workspace: {artifact!r}"
    if unresolved.is_symlink():
        return "EVIDENCE_SYMLINK", f"{label} must not be a symlink: {artifact!r}"
    if not candidate.is_file():
        return "EVIDENCE_ARTIFACT_MISSING", f"{label} does not exist: {artifact!r}"
    expected = "sha256:" + sha256(candidate)
    if integrity != expected:
        return "EVIDENCE_INTEGRITY", f"{label} integrity does not match {artifact!r}"
    return None


def evidence_artifact_issue(entry: dict[str, object], root: Path, contracts: dict[str, str]) -> tuple[str, str] | None:
    artifact = entry.get("artifact")
    integrity = entry.get("integrity")
    if entry.get("contract_integrity") != contracts_integrity(contracts):
        return "EVIDENCE_CONTRACT", "current PASS evidence does not match the task's current contract snapshot"
    artifact_issue = local_artifact_issue(artifact, integrity, root, "evidence artifact")
    if artifact_issue is not None:
        return artifact_issue
    manifest = entry.get("manifest")
    manifest_integrity = entry.get("manifest_integrity")
    manifest_issue = local_artifact_issue(manifest, manifest_integrity, root, "evidence manifest")
    if manifest_issue is not None:
        return manifest_issue
    try:
        manifest_data = strict_json_loads((root / str(manifest)).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return "EVIDENCE_MANIFEST", "evidence manifest must contain valid JSON"
    expected_manifest = {
        "schema_version": 1,
        "check": entry.get("check"),
        "result": entry.get("result"),
        "summary": entry.get("summary"),
        "artifact": artifact,
        "integrity": integrity,
        "contracts": contracts,
    }
    if manifest_data != expected_manifest:
        return "EVIDENCE_MANIFEST", "evidence manifest does not bind the check, result, artifact, and current contracts"
    return None


def canonical_path_prefix(resource: str, root: Path) -> str | None:
    kind, value = resource_base(resource)
    if kind != "path":
        return None
    prefix = fixed_glob_prefix(value) if any(char in value for char in GLOB_META) else value
    candidate = (root / prefix).resolve()
    try:
        return candidate.relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def overlaps_at_root(left: str, right: str, root: Path) -> bool:
    left_kind, _ = resource_base(left)
    right_kind, _ = resource_base(right)
    if left_kind != "path" or right_kind != "path":
        return overlaps(left, right)
    left_prefix = canonical_path_prefix(left, root)
    right_prefix = canonical_path_prefix(right, root)
    if left_prefix is None or right_prefix is None:
        return True
    return left_prefix == right_prefix or left_prefix.startswith(right_prefix + "/") or right_prefix.startswith(left_prefix + "/")


def criterion_passes(criterion: object, root: Path, contracts: dict[str, str]) -> bool:
    if not isinstance(criterion, dict):
        return False
    evidence = criterion.get("evidence", [])
    return any(
        isinstance(item, dict)
        and item.get("result") == "PASS"
        and item.get("current") is True
        and evidence_artifact_issue(item, root, contracts) is None
        for item in evidence
    )


def parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return None


def validate(data: object, root: Path | None = None, now: datetime | None = None) -> list[Issue]:
    issues: list[Issue] = []
    root = (root or Path.cwd()).resolve()
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(data, dict):
        return [Issue("ROOT", "ledger must be a JSON object")]
    unknown_root_fields = set(data) - TOP_LEVEL_FIELDS
    missing_root_fields = TOP_LEVEL_FIELDS - set(data)
    if unknown_root_fields or missing_root_fields:
        issues.append(Issue("ROOT_FIELDS", f"root fields mismatch (missing={sorted(missing_root_fields)}, unknown={sorted(unknown_root_fields)})"))
    if data.get("schema_version") != 3:
        issues.append(Issue("SCHEMA_VERSION", "schema_version must equal 3"))
    if not isinstance(data.get("goal"), str) or not data.get("goal", "").strip():
        issues.append(Issue("GOAL", "goal must be a non-empty string"))
    contracts = data.get("contracts", {})
    limits = data.get("limits", {})
    evidence_registry = data.get("evidence_registry", {})
    tasks = data.get("tasks", [])
    if not isinstance(contracts, dict) or not all(isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip() for key, value in contracts.items()):
        issues.append(Issue("CONTRACTS", "contracts must map names to versions"))
        contracts = {}
    expected_limits = {"max_attempts_per_task", "max_checkpoint_age_seconds"}
    if not isinstance(limits, dict) or set(limits) != expected_limits:
        issues.append(Issue("LIMIT_FIELDS", f"limits must contain exactly {sorted(expected_limits)}"))
    valid_evidence_refs: set[str] = set()
    if not isinstance(evidence_registry, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in evidence_registry.items()):
        issues.append(Issue("EVIDENCE_REGISTRY", "evidence_registry must map sha256 digests to local artifact paths"))
        evidence_registry = {}
    else:
        for integrity, artifact in evidence_registry.items():
            if not SHA256_RE.fullmatch(integrity):
                issues.append(Issue("EVIDENCE_REGISTRY", f"invalid evidence registry digest {integrity!r}"))
                continue
            artifact_issue = local_artifact_issue(artifact, integrity, root, "registered evidence")
            if artifact_issue is not None:
                code, message = artifact_issue
                issues.append(Issue(code, message))
                continue
            valid_evidence_refs.add(integrity)
    max_attempts = limits.get("max_attempts_per_task") if isinstance(limits, dict) else None
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10:
        issues.append(Issue("LIMITS", "max_attempts_per_task must be an integer from 1 to 10"))
        max_attempts = 1
    max_checkpoint_age = limits.get("max_checkpoint_age_seconds") if isinstance(limits, dict) else None
    if not isinstance(max_checkpoint_age, int) or isinstance(max_checkpoint_age, bool) or not 30 <= max_checkpoint_age <= 3600:
        issues.append(Issue("LIMITS", "max_checkpoint_age_seconds must be an integer from 30 to 3600"))
        max_checkpoint_age = 300
    if not isinstance(tasks, list) or not tasks:
        issues.append(Issue("TASKS", "tasks must be a non-empty array"))
        return issues

    by_id: dict[str, dict[str, object]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            issues.append(Issue("TASK_SHAPE", "each task must be an object"))
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or not ID_RE.fullmatch(task_id):
            issues.append(Issue("TASK_ID", "task id must match ^[A-Z][A-Z0-9_-]*$", str(task_id)))
            continue
        if task_id in by_id:
            issues.append(Issue("TASK_DUPLICATE", "duplicate task id", task_id))
        else:
            by_id[task_id] = task

    for task_id, task in by_id.items():
        status = task.get("status")
        if status not in STATUSES:
            issues.append(Issue("STATUS", f"invalid status {status!r}", task_id))
            continue
        expected_task_keys = TASK_FIELDS | ({"blocked_on"} if status == "BLOCKED" else set()) | ({"execution"} if status == "RUNNING" else set())
        if set(task) != expected_task_keys:
            issues.append(
                Issue(
                    "TASK_FIELDS",
                    f"fields mismatch (missing={sorted(expected_task_keys - set(task))}, unknown={sorted(set(task) - expected_task_keys)})",
                    task_id,
                )
            )
        execution = task.get("execution")
        if status == "RUNNING":
            if not isinstance(execution, dict) or set(execution) != EXECUTION_FIELDS:
                issues.append(Issue("EXECUTION_FIELDS", f"RUNNING task requires exact execution fields {sorted(EXECUTION_FIELDS)}", task_id))
            else:
                if not isinstance(execution.get("process_id"), int) or isinstance(execution.get("process_id"), bool) or execution["process_id"] < 1:
                    issues.append(Issue("PROCESS_IDENTITY", "process_id must be a positive integer", task_id))
                if not isinstance(execution.get("process_start_token"), str) or not execution["process_start_token"].strip():
                    issues.append(Issue("PROCESS_IDENTITY", "process_start_token is required to prevent PID reuse", task_id))
                observed_at = parse_utc_timestamp(execution.get("observed_at"))
                if observed_at is None:
                    issues.append(Issue("CHECKPOINT_TIME", "observed_at must be an ISO-8601 UTC timestamp", task_id))
                else:
                    age = (current_time.astimezone(timezone.utc) - observed_at).total_seconds()
                    if age < -5:
                        issues.append(Issue("CHECKPOINT_FUTURE", "RUNNING checkpoint is dated in the future", task_id))
                    elif age > max_checkpoint_age:
                        issues.append(Issue("CHECKPOINT_STALE", f"RUNNING checkpoint is older than {max_checkpoint_age} seconds", task_id))
                if not isinstance(execution.get("checkpoint_generation"), int) or isinstance(execution.get("checkpoint_generation"), bool) or execution["checkpoint_generation"] < 1:
                    issues.append(Issue("CHECKPOINT_GENERATION", "checkpoint_generation must be a positive integer", task_id))
                for field in ("workspace_fingerprint", "artifact_fingerprint"):
                    if not isinstance(execution.get(field), str) or not SHA256_RE.fullmatch(execution[field]):
                        issues.append(Issue("CHECKPOINT_FINGERPRINT", f"{field} must be a sha256 digest", task_id))
                if not isinstance(execution.get("observer"), str) or not execution["observer"].strip():
                    issues.append(Issue("PROCESS_OBSERVER", "observer is required", task_id))
        dependencies = task.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies):
            issues.append(Issue("DEPENDENCIES", "dependencies must be a string array", task_id))
            dependencies = []
        if len(dependencies) != len(set(dependencies)):
            issues.append(Issue("DEPENDENCY_DUPLICATE", "dependencies must be unique", task_id))
        for dependency in dependencies:
            if dependency == task_id:
                issues.append(Issue("DEPENDENCY_SELF", "task depends on itself", task_id))
            elif dependency not in by_id:
                issues.append(Issue("DEPENDENCY_UNKNOWN", f"unknown dependency {dependency}", task_id))
            elif status not in {"PENDING", "BLOCKED", "FAILED"} and by_id[dependency].get("status") not in SATISFIED_DEPENDENCY:
                issues.append(Issue("DEPENDENCY_UNSATISFIED", f"dependency {dependency} is not VERIFIED or DONE", task_id))

        expected_contracts = task.get("contracts", {})
        if not isinstance(expected_contracts, dict) or not all(isinstance(name, str) and name.strip() and isinstance(version, str) and version.strip() for name, version in expected_contracts.items()):
            issues.append(Issue("TASK_CONTRACTS", "contracts must map names to versions", task_id))
        else:
            for name, version in expected_contracts.items():
                if contracts.get(name) != version:
                    issues.append(Issue("CONTRACT_STALE", f"contract {name!r} expects {version!r}, current is {contracts.get(name)!r}", task_id))

        criteria = task.get("criteria", [])
        if not isinstance(criteria, list):
            issues.append(Issue("CRITERIA", "criteria must be an array", task_id))
            criteria = []
        criterion_ids: set[str] = set()
        for criterion in criteria:
            if not isinstance(criterion, dict):
                issues.append(Issue("CRITERION_SHAPE", "criterion must be an object", task_id))
                continue
            if set(criterion) != {"id", "required", "evidence"}:
                issues.append(Issue("CRITERION_FIELDS", "criterion fields must be exactly id, required, and evidence", task_id))
            criterion_id = criterion.get("id")
            if not isinstance(criterion_id, str) or not ID_RE.fullmatch(criterion_id):
                issues.append(Issue("CRITERION_ID", f"invalid criterion id {criterion_id!r}", task_id))
            elif criterion_id in criterion_ids:
                issues.append(Issue("CRITERION_DUPLICATE", f"duplicate criterion {criterion_id}", task_id))
            else:
                criterion_ids.add(criterion_id)
            if not isinstance(criterion.get("required"), bool):
                issues.append(Issue("CRITERION_REQUIRED", f"criterion {criterion_id} requires a boolean required field", task_id))
            evidence = criterion.get("evidence")
            if not isinstance(evidence, list):
                issues.append(Issue("EVIDENCE_SHAPE", f"criterion {criterion_id} evidence must be an array", task_id))
                continue
            current_entries = [entry for entry in evidence if isinstance(entry, dict) and entry.get("current") is True]
            if len(current_entries) > 1:
                issues.append(Issue("EVIDENCE_CURRENT_CONFLICT", f"criterion {criterion_id} has more than one current evidence record", task_id))
            for entry in evidence:
                required_evidence = {"check", "result", "summary", "artifact", "integrity", "contract_integrity", "manifest", "manifest_integrity", "current"}
                if not isinstance(entry, dict) or set(entry) != required_evidence:
                    issues.append(Issue("EVIDENCE_FIELDS", f"criterion {criterion_id} has malformed evidence", task_id))
                    continue
                if entry.get("result") not in {"PASS", "FAIL", "NOT RUN"} or not isinstance(entry.get("current"), bool):
                    issues.append(Issue("EVIDENCE_RESULT", f"criterion {criterion_id} has invalid result/current", task_id))
                if not all(isinstance(entry.get(field), str) and entry.get(field).strip() for field in ("check", "summary")):
                    issues.append(Issue("EVIDENCE_TEXT", f"criterion {criterion_id} needs check and summary", task_id))
                if entry.get("result") == "PASS" and entry.get("current") is True:
                    artifact_issue = evidence_artifact_issue(entry, root, expected_contracts)
                    if artifact_issue is not None:
                        code, message = artifact_issue
                        issues.append(Issue(code, f"criterion {criterion_id}: {message}", task_id))
        if status in {"VERIFIED", "DONE"}:
            required = [item for item in criteria if isinstance(item, dict) and item.get("required") is True]
            if not required:
                issues.append(Issue("CRITERIA_REQUIRED", "VERIFIED/DONE task needs at least one required criterion", task_id))
            for criterion in required:
                if not criterion_passes(criterion, root, expected_contracts):
                    issues.append(Issue("EVIDENCE_MISSING", f"criterion {criterion.get('id')} lacks current PASS evidence", task_id))

        attempts = task.get("attempts", [])
        if not isinstance(attempts, list):
            issues.append(Issue("ATTEMPTS", "attempts must be an array", task_id))
            attempts = []
        for attempt in attempts:
            required_attempt_fields = ("outcome", "hypothesis_id", "hypothesis", "evidence_delta", "evidence_refs")
            if (
                not isinstance(attempt, dict)
                or set(attempt) != {"number", *required_attempt_fields}
                or not isinstance(attempt.get("number"), int)
                or not all(isinstance(attempt.get(field), str) and attempt.get(field, "").strip() for field in ("outcome", "hypothesis", "evidence_delta"))
                or not isinstance(attempt.get("hypothesis_id"), str)
                or not ID_RE.fullmatch(attempt.get("hypothesis_id", ""))
                or not isinstance(attempt.get("evidence_refs"), list)
                or any(not isinstance(item, str) or not SHA256_RE.fullmatch(item) for item in attempt.get("evidence_refs", []))
                or len(attempt.get("evidence_refs", [])) != len(set(attempt.get("evidence_refs", [])))
            ):
                issues.append(Issue("ATTEMPT_SHAPE", "attempt needs number, outcome, hypothesis_id, hypothesis, evidence_delta, and valid evidence_refs", task_id))
            if isinstance(attempt, dict) and isinstance(attempt.get("evidence_refs"), list):
                for reference in attempt["evidence_refs"]:
                    if isinstance(reference, str) and SHA256_RE.fullmatch(reference) and reference not in valid_evidence_refs:
                        issues.append(Issue("EVIDENCE_REF_UNKNOWN", f"attempt references unregistered evidence {reference}", task_id))
        numbers = [item.get("number") for item in attempts if isinstance(item, dict)]
        if numbers != list(range(1, len(numbers) + 1)):
            issues.append(Issue("ATTEMPT_SEQUENCE", "attempt numbers must be contiguous from 1", task_id))
        if len(attempts) > max_attempts:
            issues.append(Issue("ATTEMPT_LIMIT", f"attempt count exceeds limit {max_attempts}", task_id))
        comparable = [
            (
                str(item.get("hypothesis_id", "")),
                re.sub(r"[^\w]+", " ", str(item.get("hypothesis", "")).casefold()).strip(),
                {reference for reference in item.get("evidence_refs", []) if isinstance(reference, str) and SHA256_RE.fullmatch(reference)},
            )
            for item in attempts
            if isinstance(item, dict)
        ]
        for previous, current in zip(comparable, comparable[1:]):
            same_hypothesis = previous[0] == current[0]
            if previous[1] == current[1] and not same_hypothesis:
                issues.append(Issue("HYPOTHESIS_ID_REBOUND", "equivalent hypothesis text cannot be assigned a new hypothesis_id", task_id))
            if same_hypothesis and previous[1] != current[1]:
                issues.append(Issue("HYPOTHESIS_MUTATED", "a stable hypothesis_id cannot change its hypothesis text", task_id))
            no_new_evidence = current[2].issubset(previous[2])
            if same_hypothesis and no_new_evidence:
                issues.append(Issue("ATTEMPT_UNCHANGED", "retry repeats the same hypothesis without new evidence", task_id))
        if status == "FAILED" and len(attempts) < max_attempts:
            issues.append(Issue("FAILED_EARLY", "FAILED requires exhausted attempts", task_id))
        if status in {"RUNNING", "IMPLEMENTED", "REVIEW", "REWORK", "VERIFIED", "DONE", "FAILED"} and not attempts:
            issues.append(Issue("ATTEMPT_MISSING", f"{status} task requires attempt history", task_id))

        history = task.get("history", [])
        if not isinstance(history, list) or not history:
            issues.append(Issue("HISTORY", "history must be a non-empty status array", task_id))
        else:
            if history[0] != "PENDING":
                issues.append(Issue("HISTORY_START", "history must begin at PENDING", task_id))
            for state in history:
                if state not in STATUSES:
                    issues.append(Issue("HISTORY_STATUS", f"invalid history status {state!r}", task_id))
            if history[-1] != status:
                issues.append(Issue("HISTORY_CURRENT", "last history state must equal current status", task_id))
            for previous, current in zip(history, history[1:]):
                if previous not in TRANSITIONS or current not in TRANSITIONS.get(previous, set()):
                    issues.append(Issue("TRANSITION", f"invalid transition {previous} -> {current}", task_id))
            if status in {"VERIFIED", "DONE"}:
                required_chain = ["PENDING", "READY", "RUNNING", "IMPLEMENTED", "REVIEW", "VERIFIED"]
                if status == "DONE":
                    required_chain.append("DONE")
                cursor = iter(history)
                if not all(any(state == required for state in cursor) for required in required_chain):
                    issues.append(Issue("HISTORY_CHAIN", f"{status} history omits required lifecycle stages", task_id))

        findings = task.get("open_findings", [])
        if not isinstance(findings, list):
            issues.append(Issue("FINDINGS", "open_findings must be an array", task_id))
        elif status == "DONE" and any(isinstance(item, dict) and item.get("severity") in {"critical", "high"} for item in findings):
            issues.append(Issue("DONE_FINDING", "DONE task has critical/high open finding", task_id))
        if isinstance(findings, list):
            for finding in findings:
                if (
                    not isinstance(finding, dict)
                    or set(finding) != {"severity", "summary"}
                    or finding.get("severity") not in {"critical", "high", "medium", "low"}
                    or not isinstance(finding.get("summary"), str)
                    or not finding.get("summary", "").strip()
                ):
                    issues.append(Issue("FINDING_SHAPE", "finding needs severity and summary", task_id))
        owns = task.get("owns", [])
        if not isinstance(owns, list) or not all(isinstance(resource, str) and resource.strip() for resource in owns):
            issues.append(Issue("OWNERSHIP_SHAPE", "owns must be an array of non-empty strings", task_id))
        else:
            normalized_owns = [resource_base(resource) for resource in owns]
            if len(normalized_owns) != len(set(normalized_owns)):
                issues.append(Issue("OWNERSHIP_DUPLICATE", "owned resources must be unique", task_id))
            for resource in owns:
                kind, value = resource_base(resource)
                raw_parts = PurePosixPath(resource.split(":", 1)[-1].replace("\\", "/")).parts
                if kind == "path" and (value.startswith("/") or ".." in raw_parts or canonical_path_prefix(resource, root) is None):
                    issues.append(Issue("OWNERSHIP_ESCAPE", f"owned path escapes workspace: {resource!r}", task_id))
        if status == "BLOCKED" and (not isinstance(task.get("blocked_on"), str) or not task.get("blocked_on", "").strip()):
            issues.append(Issue("BLOCKED_REASON", "BLOCKED task needs blocked_on", task_id))
        if status == "DONE":
            for dependency in dependencies:
                if dependency in by_id and by_id[dependency].get("status") != "DONE":
                    issues.append(Issue("DONE_DEPENDENCY", f"DONE requires dependency {dependency} to be DONE", task_id))

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            issues.append(Issue("DEPENDENCY_CYCLE", "dependency cycle detected", task_id))
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].get("dependencies", []):
            if dependency in by_id:
                visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in by_id:
        visit(task_id)

    active = [(task_id, task) for task_id, task in by_id.items() if task.get("status") in ACTIVE]
    process_identities: set[tuple[int, str]] = set()
    for task_id, task in active:
        execution = task.get("execution")
        if isinstance(execution, dict) and isinstance(execution.get("process_id"), int) and isinstance(execution.get("process_start_token"), str):
            identity = (execution["process_id"], execution["process_start_token"])
            if identity in process_identities:
                issues.append(Issue("PROCESS_IDENTITY_COLLISION", "active tasks cannot claim the same process identity", task_id))
            process_identities.add(identity)
    for index, (left_id, left) in enumerate(active):
        for right_id, right in active[index + 1 :]:
            left_owns = left.get("owns", []) if isinstance(left.get("owns", []), list) else []
            right_owns = right.get("owns", []) if isinstance(right.get("owns", []), list) else []
            for left_resource in left_owns:
                for right_resource in right_owns:
                    if isinstance(left_resource, str) and isinstance(right_resource, str) and overlaps_at_root(left_resource, right_resource, root):
                        issues.append(Issue("OWNERSHIP_COLLISION", f"{left_resource!r} overlaps {right_resource!r} owned by {right_id}", left_id))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        data = strict_json_loads(args.state.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"validate_state: FAIL ({exc})")
        return 1
    issues = validate(data, Path.cwd(), datetime.now(timezone.utc))
    if args.as_json:
        print(json.dumps({"passed": not issues, "issues": [asdict(issue) for issue in issues]}, indent=2))
    else:
        for issue in issues:
            label = f" task={issue.task}" if issue.task else ""
            print(f"ERROR {issue.code}{label}: {issue.message}")
        print(f"validate_state: {'PASS' if not issues else 'FAIL'} ({len(issues)} issues)")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
