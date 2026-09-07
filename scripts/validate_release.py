#!/usr/bin/env python3
"""Evaluate release-only gates without treating development checks as approval."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.calibrate_labels import calibrate as calibrate_humans
    from scripts.calibrate_labels import validate_labeler_registry, validate_labels
    from scripts.build_plugin import build
    from scripts.compare_operations import compare as compare_operations
    from scripts.compare_operations import load_jsonl as load_operational_runs
    from scripts.compare_operations import validate_runs as validate_operational_runs
    from scripts.run_evals import load_jsonl as load_eval_jsonl
    from scripts.run_evals import score as score_routing
    from scripts.run_evals import validate_cases, validate_predictions
    from scripts.json_strict import loads as strict_json_loads
    from scripts.signed_attestation import external_evidence_file, external_trust_anchor, load_signed_statement, principals_have_distinct_keys
    from scripts.validate_client_smoke import validate as validate_client_smoke
    from scripts.verify_codex_runtime_probe import verify_probe_bundle
    from scripts.verify_codex_routing_probe import verify as verify_routing_probe
    from scripts.validate_runtime_safety import summarize as summarize_runtime_safety
    from scripts.smoke_plugin import smoke
    from scripts.validate_routing_receipt import validate as validate_routing_receipt
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from calibrate_labels import calibrate as calibrate_humans
    from calibrate_labels import validate_labeler_registry, validate_labels
    from build_plugin import build
    from compare_operations import compare as compare_operations
    from compare_operations import load_jsonl as load_operational_runs
    from compare_operations import validate_runs as validate_operational_runs
    from run_evals import load_jsonl as load_eval_jsonl
    from run_evals import score as score_routing
    from run_evals import validate_cases, validate_predictions
    from json_strict import loads as strict_json_loads
    from signed_attestation import external_evidence_file, external_trust_anchor, load_signed_statement, principals_have_distinct_keys
    from validate_client_smoke import validate as validate_client_smoke
    from verify_codex_runtime_probe import verify_probe_bundle
    from verify_codex_routing_probe import verify as verify_routing_probe
    from validate_runtime_safety import summarize as summarize_runtime_safety
    from smoke_plugin import smoke
    from validate_routing_receipt import validate as validate_routing_receipt


# This trust-boundary inventory is deliberately validator-owned. Never import it
# from the builder that it authenticates.
RELEASE_INPUT_FILES = (
    "VERSION",
    "packaging/plugin.template.json",
    "scripts/build_plugin.py",
    "scripts/calibrate_labels.py",
    "scripts/compare_operations.py",
    "scripts/run_codex_routing_probe.py",
    "scripts/run_codex_runtime_probe.py",
    "scripts/validate_release.py",
    "scripts/signed_attestation.py",
    "scripts/verify_release_authority.py",
    "scripts/validate_client_smoke.py",
    "scripts/validate_routing_receipt.py",
    "scripts/validate_runtime_safety.py",
    "scripts/validate_trace.py",
    "scripts/verify_codex_runtime_probe.py",
    "scripts/verify_codex_routing_probe.py",
    "scripts/run_evals.py",
    "scripts/smoke_plugin.py",
    "scripts/validate_skill.py",
    "SKILL.md",
    "agents/openai.yaml",
    "assets/icon-large.svg",
    "assets/icon-small.svg",
    "references/agent-brief.md",
    "references/delegation.md",
    "references/orchestration-workflow.md",
    "references/recovery.md",
    "references/security.md",
    "references/task-graph.md",
    "references/verification.md",
    "scripts/evidence_digest.py",
    "scripts/json_strict.py",
    "scripts/validate_state.py",
    "schemas/orchestration-state.schema.json",
    "schemas/action-trace.schema.json",
    "schemas/client-smoke-output.schema.json",
    "schemas/codex-routing-probe-output.schema.json",
    "schemas/codex-runtime-probe-output.schema.json",
    "schemas/human-label.schema.json",
    "schemas/labeler-registry.schema.json",
    "schemas/operational-run.schema.json",
    "schemas/runtime-safety-report.schema.json",
    "schemas/release-attestation.schema.json",
    "config/budgets.json",
    "config/eval-thresholds.json",
    "config/operational-thresholds.json",
    "config/release-policy.json",
    "config/release-quality-bar.json",
    "evals/runtime-scenarios/v1/app.log",
    "evals/runtime-scenarios/v1/code.py",
    "evals/runtime-scenarios/v1/code-write.py",
    "evals/runtime-scenarios/v1/docs.md",
    "evals/runtime-scenarios/v1/issue.md",
    "evals/runtime-scenarios/v1/recovery-state.json",
    "evals/runtime-scenarios/v1/tool-output.txt",
    "LICENSE.md",
    "RELEASE_NOTES.md",
)

REQUIRED_RELEASE_GATES = (
    "retained-artifact",
    "release-materials",
    "clean-worktree",
    "committed-canonical-layout",
    "head-source-identity",
    "release-policy",
    "budget-approval",
    "external-distribution-approval",
    "routing-evidence",
    "routing-provenance",
    "runtime-safety-evidence",
    "operational-evidence",
    "aaa-human-calibration",
    "supported-client-scope",
    "independent-approval",
    "ci-provenance",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_symlink_component(path: Path, root: Path) -> bool:
    """Reject evidence reached through any symlink below the trust root."""
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


def has_absolute_symlink_component(path: Path) -> bool:
    """Detect symlinks in an arbitrary artifact path without resolving them away."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def check(name: str, passed: bool, summary: str) -> dict[str, object]:
    return {"name": name, "passed": passed, "status": "PASS" if passed else "FAIL", "summary": summary}


def git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=root, text=True, capture_output=True, check=False)


def head_release_inputs_match(root: Path) -> tuple[bool, str]:
    """Compare every tracked byte with HEAD, bypassing index concealment flags."""
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if listing.returncode != 0:
        return False, "unable to enumerate HEAD"
    tracked = {item.decode("utf-8", errors="surrogateescape") for item in listing.stdout.split(b"\0") if item}
    mismatches: list[str] = []
    missing_inputs = sorted(set(RELEASE_INPUT_FILES) - tracked)
    for relative in sorted(tracked):
        source = root / relative
        blob = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if blob.returncode != 0 or not source.is_file() or source.is_symlink() or source.read_bytes() != blob.stdout:
            mismatches.append(relative)
    if missing_inputs or mismatches:
        return False, f"required inputs missing from HEAD={missing_inputs}; tracked bytes differing from HEAD={mismatches}"
    return True, f"all {len(tracked)} tracked files, including {len(RELEASE_INPUT_FILES)} required release inputs, match HEAD exactly"


def load_report(path: Path) -> dict[str, object] | None:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def signed_release_statement(
    root: Path,
    environment: dict[str, str],
    role_prefix: str,
    allowed_signers: Path | None,
    *,
    now: datetime | None = None,
) -> dict[str, object] | None:
    """Load one externally supplied, externally trusted release statement."""
    if allowed_signers is None:
        return None
    prefix = f"ORCHESTRATE_{role_prefix.upper()}"
    statement_path = external_evidence_file(root, environment, f"{prefix}_ATTESTATION")
    signature_path = external_evidence_file(root, environment, f"{prefix}_SIGNATURE")
    principal = environment.get(f"{prefix}_PRINCIPAL", "")
    if statement_path is None or signature_path is None or not principal:
        return None
    return load_signed_statement(statement_path, signature_path, allowed_signers, principal, now=now)


def current_product_attestation(
    root: Path,
    environment: dict[str, str],
    allowed_signers: Path | None,
    head: str,
    artifact_sha256: str,
    *,
    now: datetime | None = None,
) -> dict[str, object] | None:
    statement = signed_release_statement(root, environment, "product_owner", allowed_signers, now=now)
    expected_fields = {
        "schema_version", "role", "principal", "issued_at", "head", "skill_sha256",
        "artifact_sha256", "quality_bar_sha256", "budgets_sha256",
        "operational_thresholds_sha256", "external_distribution_approved",
        "human_labeler_principals",
    }
    if statement is None or set(statement) != expected_fields:
        return None
    labelers = statement.get("human_labeler_principals")
    expected = {
        "schema_version": 1,
        "role": "product-owner",
        "principal": environment.get("ORCHESTRATE_PRODUCT_OWNER_PRINCIPAL", ""),
        "head": head,
        "skill_sha256": sha256(root / "SKILL.md"),
        "artifact_sha256": artifact_sha256,
        "quality_bar_sha256": sha256(root / "config" / "release-quality-bar.json"),
        "budgets_sha256": sha256(root / "config" / "budgets.json"),
        "operational_thresholds_sha256": sha256(root / "config" / "operational-thresholds.json"),
        "external_distribution_approved": True,
    }
    if any(statement.get(key) != value for key, value in expected.items()):
        return None
    if (
        not isinstance(labelers, list)
        or len(labelers) < 2
        or len(labelers) != len(set(str(item) for item in labelers))
        or any(not isinstance(item, str) or not item.strip() for item in labelers)
        or statement.get("principal") in labelers
        or environment.get("ORCHESTRATE_FINAL_VERIFIER_PRINCIPAL", "") in labelers
        or environment.get("ORCHESTRATE_FINAL_VERIFIER_PRINCIPAL", "") == statement.get("principal")
    ):
        return None
    if allowed_signers is None or not principals_have_distinct_keys(
        allowed_signers,
        [str(statement["principal"]), environment.get("ORCHESTRATE_FINAL_VERIFIER_PRINCIPAL", ""), *labelers],
    ):
        return None
    return statement


def current_final_attestation(
    root: Path,
    environment: dict[str, str],
    allowed_signers: Path | None,
    head: str,
    artifact_sha256: str,
    product_statement_path: Path | None,
    product_signature_path: Path | None,
    product_statement: dict[str, object] | None,
    *,
    now: datetime | None = None,
) -> dict[str, object] | None:
    statement = signed_release_statement(root, environment, "final_verifier", allowed_signers, now=now)
    expected_fields = {
        "schema_version", "role", "principal", "issued_at", "head", "skill_sha256",
        "artifact_sha256", "quality_bar_sha256", "product_attestation_sha256",
        "product_signature_sha256", "verdict",
    }
    if (
        statement is None
        or product_statement is None
        or product_statement_path is None
        or product_signature_path is None
        or set(statement) != expected_fields
    ):
        return None
    expected = {
        "schema_version": 1,
        "role": "independent-verifier",
        "principal": environment.get("ORCHESTRATE_FINAL_VERIFIER_PRINCIPAL", ""),
        "head": head,
        "skill_sha256": sha256(root / "SKILL.md"),
        "artifact_sha256": artifact_sha256,
        "quality_bar_sha256": sha256(root / "config" / "release-quality-bar.json"),
        "product_attestation_sha256": sha256(product_statement_path),
        "product_signature_sha256": sha256(product_signature_path),
        "verdict": "APPROVE",
    }
    if any(statement.get(key) != value for key, value in expected.items()):
        return None
    if statement.get("principal") == product_statement.get("principal"):
        return None
    if allowed_signers is None or not principals_have_distinct_keys(
        allowed_signers,
        [str(product_statement["principal"]), str(statement["principal"])],
    ):
        return None
    try:
        final_issued = datetime.fromisoformat(str(statement["issued_at"]).replace("Z", "+00:00"))
        product_issued = datetime.fromisoformat(str(product_statement["issued_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    if (
        final_issued.tzinfo is None
        or product_issued.tzinfo is None
        or final_issued.astimezone(timezone.utc) <= product_issued.astimezone(timezone.utc)
    ):
        return None
    return statement


def tracked_regular_evidence(root: Path, relative: object, expected_sha256: object) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return None
    if (
        has_symlink_component(candidate, root)
        or not resolved.is_file()
        or expected_sha256 != sha256(resolved)
        or git(root, "ls-files", "--error-unmatch", relative).returncode != 0
    ):
        return None
    return resolved


def current_routing_report(root: Path, report: dict[str, object] | None, evidence_version: str = "routing-v2") -> bool:
    if evidence_version not in {"routing-v2", "routing-v3"}:
        return False
    relative_report = f"evals/reports/{evidence_version}.json"
    if (
        report is None
        or report.get("passed") is not True
        or report.get("evidence_scope") != "routing-classification-only"
        or report.get("release_authority") is not False
        or git(root, "ls-files", "--error-unmatch", relative_report).returncode != 0
    ):
        return False
    provenance = report.get("provenance")
    prediction_files = provenance.get("prediction_files") if isinstance(provenance, dict) else None
    if not isinstance(prediction_files, list) or not prediction_files or provenance.get("prediction_source") != "blind-evaluator-output":
        return False
    dataset = root / "evals" / "cases.jsonl"
    thresholds_path = root / "config" / "eval-thresholds.json"
    if (
        provenance.get("dataset_sha256") != sha256(dataset)
        or provenance.get("thresholds_sha256") != sha256(thresholds_path)
    ):
        return False
    paths: list[Path] = []
    for item in prediction_files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            return False
        path = tracked_regular_evidence(root, item.get("path"), item.get("sha256"))
        if path is None or path in paths:
            return False
        paths.append(path)
    try:
        cases = load_eval_jsonl(dataset)
        thresholds = strict_json_loads(thresholds_path.read_text(encoding="utf-8"))
        if not isinstance(thresholds, dict):
            return False
        minimum_runs = int(thresholds["release_min_runs_per_case"])
        predictions = [record for path in paths for record in load_eval_jsonl(path)]
        if validate_cases(cases, thresholds) or validate_predictions(predictions, {str(case["id"]) for case in cases}, minimum_runs):
            return False
        recomputed = score_routing(cases, predictions, thresholds, minimum_runs)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False
    return all(report.get(key) == value for key, value in recomputed.items())


def current_operational_report(root: Path, report: dict[str, object] | None, artifact_sha256: str) -> bool:
    if (
        report is None
        or report.get("passed") is not True
        or report.get("evidence_scope") != "paired-task-execution"
        or report.get("release_eligible_measurements") is not True
        or report.get("threshold_approval") != "product-owner-approved"
        or report.get("source_sha256") != sha256(root / "SKILL.md")
        or report.get("artifact_sha256") != artifact_sha256
        or git(root, "ls-files", "--error-unmatch", "evals/reports/operations-v2.json").returncode != 0
    ):
        return False
    provenance = report.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("thresholds") != "config/operational-thresholds.json":
        return False
    runs_relative = provenance.get("runs")
    if not isinstance(runs_relative, str) or not runs_relative or Path(runs_relative).is_absolute():
        return False
    thresholds_path = root / "config" / "operational-thresholds.json"
    runs_path = tracked_regular_evidence(root, runs_relative, provenance.get("runs_sha256"))
    if runs_path is None or has_symlink_component(thresholds_path, root) or provenance.get("thresholds_sha256") != sha256(thresholds_path):
        return False
    try:
        thresholds = strict_json_loads(thresholds_path.read_text(encoding="utf-8"))
        if not isinstance(thresholds, dict) or thresholds.get("approval_status") != "product-owner-approved":
            return False
        records = load_operational_runs(runs_path)
        if validate_operational_runs(records, int(thresholds["minimum_runs_per_configuration"])):
            return False
        if any(
            record.get("measurement_source") == "fixture"
            or record.get("candidate_source_sha256") != report["source_sha256"]
            or record.get("candidate_artifact_sha256") != artifact_sha256
            for record in records
        ):
            return False
        recomputed = compare_operations(records, thresholds)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False
    # Every decision-bearing summary value is derived again from the bound raw runs.
    return all(report.get(key) == value for key, value in recomputed.items())


def current_runtime_safety_report(
    root: Path,
    report: dict[str, object] | None,
    artifact: Path,
    supported_clients: list[object],
) -> bool:
    if (
        report is None
        or report.get("passed") is not True
        or report.get("release_eligible_measurements") is not True
        or report.get("evidence_scope") != "observed-runtime-side-effects"
        or report.get("client") not in supported_clients
        or not isinstance(report.get("client_version"), str)
        or not isinstance(report.get("measurement_source"), str)
        or not isinstance(report.get("environment"), str)
        or not isinstance(report.get("observer_attestation"), str)
        or git(root, "ls-files", "--error-unmatch", "evals/reports/runtime-safety-v2.json").returncode != 0
    ):
        return False
    provenance = report.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("trace") != "evals/evidence/runtime-safety-v2/trace.jsonl":
        return False
    trace = root / "evals" / "evidence" / "runtime-safety-v2" / "trace.jsonl"
    if tracked_regular_evidence(root, "evals/evidence/runtime-safety-v2/trace.jsonl", provenance.get("trace_sha256")) is None:
        return False
    try:
        recomputed = summarize_runtime_safety(
            root,
            trace,
            artifact,
            str(report["client"]),
            str(report["client_version"]),
            str(report["measurement_source"]),
            str(report["environment"]),
            str(report["observer_attestation"]),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False
    return report == recomputed


def current_client_scope(root: Path, supported_clients: list[object], artifact: Path) -> bool:
    """Require tracked, hash-bound evidence for all five checks of each declared client."""
    artifact_sha256 = sha256(artifact) if artifact.is_file() and not artifact.is_symlink() else ""
    if len(supported_clients) != len(set(str(item) for item in supported_clients)):
        return False
    for client in supported_clients:
        if not isinstance(client, str) or not client:
            return False
        relative_report = f"evals/reports/client-smoke-{client}.json"
        report = load_report(root / relative_report)
        if (
            report is None
            or validate_client_smoke(report)
            or report.get("client") != client
            or report.get("support_status") != "SUPPORTED"
            or report.get("artifact_sha256") != artifact_sha256
            or git(root, "ls-files", "--error-unmatch", relative_report).returncode != 0
        ):
            return False
        checks = report.get("checks")
        if not isinstance(checks, list):
            return False
        seen_artifacts: set[str] = set()
        for item in checks:
            evidence_artifact = item.get("artifact") if isinstance(item, dict) else None
            if not isinstance(evidence_artifact, dict):
                return False
            relative = evidence_artifact.get("path")
            if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or relative in seen_artifacts:
                return False
            seen_artifacts.add(relative)
            candidate = root / relative
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root.resolve(strict=True))
            except (OSError, ValueError):
                return False
            if (
                has_symlink_component(candidate, root)
                or not resolved.is_file()
                or evidence_artifact.get("sha256") != sha256(resolved)
                or git(root, "ls-files", "--error-unmatch", relative).returncode != 0
            ):
                return False
        if client == "codex-cli":
            try:
                probe = verify_probe_bundle(root, artifact)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                return False
            evidence_paths = probe.get("evidence_paths")
            if not isinstance(evidence_paths, list) or not evidence_paths or any(
                not isinstance(relative, str)
                or git(root, "ls-files", "--error-unmatch", relative).returncode != 0
                for relative in evidence_paths
            ):
                return False
    return True


def current_human_calibration_report(
    root: Path,
    report: dict[str, object] | None,
    allowed_signers: Path | None = None,
    authorized_principals: set[str] | None = None,
    verifying_principal: str | None = None,
) -> bool:
    if (
        report is None
        or report.get("passed") is not True
        or report.get("release_eligible_measurements") is not True
        or report.get("evidence_scope") != "blind-human-routing-calibration"
        or git(root, "ls-files", "--error-unmatch", "evals/reports/human-calibration-v2.json").returncode != 0
    ):
        return False
    provenance = report.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("dataset") != "evals/cases.jsonl" or provenance.get("thresholds") != "config/eval-thresholds.json":
        return False
    dataset = root / "evals" / "cases.jsonl"
    thresholds_path = root / "config" / "eval-thresholds.json"
    if provenance.get("dataset_sha256") != sha256(dataset) or provenance.get("thresholds_sha256") != sha256(thresholds_path):
        return False

    def materialize_many(value: object) -> list[Path] | None:
        if not isinstance(value, list) or not value:
            return None
        result: list[Path] = []
        for item in value:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                return None
            path = tracked_regular_evidence(root, item.get("path"), item.get("sha256"))
            if path is None or path in result:
                return None
            result.append(path)
        return result

    label_paths = materialize_many(provenance.get("label_files"))
    prediction_paths = materialize_many(provenance.get("prediction_files"))
    registry_descriptor = provenance.get("labeler_registry")
    if not isinstance(registry_descriptor, dict) or set(registry_descriptor) != {"path", "sha256"}:
        return False
    registry_path = tracked_regular_evidence(root, registry_descriptor.get("path"), registry_descriptor.get("sha256"))
    if label_paths is None or prediction_paths is None or registry_path is None:
        return False
    try:
        cases = load_eval_jsonl(dataset)
        case_ids = {str(case["id"]) for case in cases}
        labels = [record for path in label_paths for record in load_eval_jsonl(path)]
        predictions = [record for path in prediction_paths for record in load_eval_jsonl(path)]
        registry = strict_json_loads(registry_path.read_text(encoding="utf-8"))
        verified_labelers, registry_errors = validate_labeler_registry(
            registry,
            registry_path.parent,
            allowed_signers,
            authorized_principals,
            verifying_principal,
        )
        if registry_errors:
            return False
        if not isinstance(registry, dict):
            return False
        for labeler in registry.get("labelers", []):
            if not isinstance(labeler, dict):
                return False
            for path_field, digest_field in (
                ("attestation_path", "attestation_sha256"),
                ("signature_path", "signature_sha256"),
            ):
                evidence = (registry_path.parent / str(labeler.get(path_field, ""))).resolve()
                try:
                    evidence_relative = evidence.relative_to(root.resolve(strict=True)).as_posix()
                except (OSError, ValueError):
                    return False
                if tracked_regular_evidence(root, evidence_relative, labeler.get(digest_field)) is None:
                    return False
        thresholds = strict_json_loads(thresholds_path.read_text(encoding="utf-8"))
        if not isinstance(thresholds, dict):
            return False
        minimum_runs = int(thresholds["release_min_runs_per_case"])
        if (
            validate_cases(cases, thresholds)
            or validate_labels(labels, case_ids, verified_labelers=verified_labelers)
            or validate_predictions(predictions, case_ids, minimum_runs)
        ):
            return False
        recomputed = calibrate_humans(labels, predictions, thresholds)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False
    return all(report.get(key) == value for key, value in recomputed.items())


def retained_artifact_check(root: Path, artifact: Path, expected: Path) -> tuple[bool, str]:
    if has_absolute_symlink_component(artifact):
        return False, f"nominated artifact path contains a symlink: {artifact}"
    if not artifact.is_file():
        return False, f"nominated artifact does not exist: {artifact}"
    try:
        smoke(artifact, root)
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        return False, f"nominated artifact failed package validation: {exc}"
    if artifact.read_bytes() != expected.read_bytes():
        return False, "nominated artifact differs from a fresh deterministic build of canonical source"
    return True, f"nominated artifact matches canonical source at sha256:{sha256(artifact)}"


def evaluate(root: Path, environment: dict[str, str] | None = None, artifact: Path | None = None) -> dict[str, object]:
    environment = dict(os.environ if environment is None else environment)
    checks: list[dict[str, object]] = []
    head_result = git(root, "rev-parse", "HEAD")
    head = head_result.stdout.strip() if head_result.returncode == 0 else ""
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    nominated_artifact = (artifact or root / "dist" / f"orchestrate-{version}.zip").absolute()
    with tempfile.TemporaryDirectory(prefix="orchestrate-release-identity-") as temporary:
        temporary_root = Path(temporary)
        expected_archive = temporary_root / f"orchestrate-{version}.zip"
        fresh = build(root, temporary_root / "orchestrate", expected_archive)
        fresh_artifact_sha256 = str(fresh["sha256"])
        retained_ok, retained_summary = retained_artifact_check(root, nominated_artifact, expected_archive)
    artifact_sha256 = sha256(nominated_artifact) if nominated_artifact.is_file() else ""
    allowed_signers = external_trust_anchor(root, environment)
    product_statement_path = external_evidence_file(root, environment, "ORCHESTRATE_PRODUCT_OWNER_ATTESTATION")
    product_signature_path = external_evidence_file(root, environment, "ORCHESTRATE_PRODUCT_OWNER_SIGNATURE")
    product_statement = current_product_attestation(
        root,
        environment,
        allowed_signers,
        head,
        artifact_sha256,
    )
    checks.append(check("retained-artifact", retained_ok, retained_summary))

    release_notes = root / "RELEASE_NOTES.md"
    license_path = root / "LICENSE.md"
    materials_ok = release_notes.is_file() and license_path.is_file() and version in release_notes.read_text(encoding="utf-8")
    checks.append(check("release-materials", materials_ok, "VERSION, release notes, and explicit license status must agree."))

    status = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    clean = status.returncode == 0 and not status.stdout.strip()
    checks.append(check("clean-worktree", clean, "Release source must have no tracked or untracked changes."))

    tracked_root = git(root, "ls-files", "--error-unmatch", "SKILL.md")
    tracked_nested = git(root, "ls-files", "--error-unmatch", "orchestrate/SKILL.md")
    layout_ok = tracked_root.returncode == 0 and tracked_nested.returncode != 0
    checks.append(check("committed-canonical-layout", layout_ok, "HEAD must track root SKILL.md and no nested legacy entrypoint."))
    head_inputs_ok, head_inputs_summary = head_release_inputs_match(root)
    checks.append(check("head-source-identity", head_inputs_ok, head_inputs_summary))

    policy = load_report(root / "config" / "release-policy.json")
    quality_bar = load_report(root / "config" / "release-quality-bar.json")
    expected_policy_fields = {
        "schema_version", "channel", "automatic_grader_release_authority", "supported_clients",
        "external_distribution_approved", "budget_approval",
    }
    policy_ok = (
        policy is not None
        and set(policy) == expected_policy_fields
        and policy.get("schema_version") == 1
        and policy.get("automatic_grader_release_authority") is False
        and isinstance(policy.get("channel"), str)
        and bool(str(policy.get("channel", "")).strip())
        and isinstance(policy.get("supported_clients"), list)
        and quality_bar is not None
        and set(quality_bar) == {"schema_version", "all_required", "required_gates"}
        and quality_bar.get("schema_version") == 1
        and quality_bar.get("all_required") is True
        and quality_bar.get("required_gates") == list(REQUIRED_RELEASE_GATES)
    )
    checks.append(check("release-policy", policy_ok, "Versioned policy and the frozen all-required release quality bar must be structurally exact."))
    budget_config = load_report(root / "config" / "budgets.json")
    budgets_approved = (
        policy is not None
        and policy.get("budget_approval") == "product-owner-approved"
        and budget_config is not None
        and budget_config.get("approval_status") == "product-owner-approved"
        and product_statement is not None
    )
    checks.append(check("budget-approval", budgets_approved, "Budget defaults require policy state plus a fresh external product-owner signature bound to HEAD and artifact."))
    distribution_approved = (
        policy is not None
        and policy.get("external_distribution_approved") is True
        and product_statement is not None
    )
    checks.append(check("external-distribution-approval", distribution_approved, "External publication requires policy state plus a fresh external product-owner signature bound to HEAD and artifact."))

    routing_path = root / "evals" / "reports" / "routing-v3.json"
    routing = load_report(routing_path)
    routing_ok = current_routing_report(root, routing, "routing-v3")
    try:
        routing_probe = verify_routing_probe(root)
        routing_ok = routing_ok and routing_probe.get("passed") is True
    except (OSError, ValueError, KeyError, AssertionError, json.JSONDecodeError):
        routing_ok = False
    checks.append(check("routing-evidence", routing_ok, "Routing evidence must pass and match the current dataset and thresholds."))

    receipt_path = root / "evals" / "evidence" / "routing-v3" / "receipt.json"
    receipt = load_report(receipt_path)
    receipt_relative = "evals/evidence/routing-v3/receipt.json"
    receipt_files_tracked = False
    if isinstance(receipt, dict):
        snapshot = receipt.get("source_snapshot")
        evaluators = receipt.get("evaluators")
        referenced = [receipt_relative]
        if isinstance(snapshot, dict) and isinstance(snapshot.get("path"), str):
            referenced.append(snapshot["path"])
        if isinstance(evaluators, list):
            for evaluator in evaluators:
                if not isinstance(evaluator, dict):
                    continue
                for field in ("output", "session_rollout", "prompt", "invocation"):
                    descriptor = evaluator.get(field)
                    if isinstance(descriptor, dict) and isinstance(descriptor.get("path"), str):
                        referenced.append(str(descriptor["path"]))
        receipt_files_tracked = len(referenced) == 14 and len(set(referenced)) == 14 and all(
            git(root, "ls-files", "--error-unmatch", relative).returncode == 0 for relative in referenced
        )
    routing_provenance_ok = (
        receipt is not None
        and not validate_routing_receipt(receipt, root)
        and receipt.get("immutable") is True
        and receipt_files_tracked
    )
    checks.append(
        check(
            "routing-provenance",
            routing_provenance_ok,
            "Blind routing evidence must have a valid receipt committed as immutable source evidence.",
        )
    )

    supported_clients = policy.get("supported_clients", []) if policy is not None else []
    if not isinstance(supported_clients, list):
        supported_clients = []
    safety_path = root / "evals" / "reports" / "runtime-safety-v2.json"
    safety = load_report(safety_path)
    runtime_safety_ok = current_runtime_safety_report(root, safety, nominated_artifact, supported_clients)
    checks.append(
        check(
            "runtime-safety-evidence",
            runtime_safety_ok,
            "QG-05 requires observed runtime-side-effect evidence for this exact skill and plugin artifact.",
        )
    )

    operations_path = root / "evals" / "reports" / "operations-v2.json"
    operations = load_report(operations_path)
    operations_ok = current_operational_report(root, operations, artifact_sha256)
    checks.append(check("operational-evidence", operations_ok, "Paired task execution must pass current product-owner-approved thresholds."))

    calibration_path = root / "evals" / "reports" / "human-calibration-v2.json"
    calibration = load_report(calibration_path)
    authorized_labelers = (
        set(str(item) for item in product_statement.get("human_labeler_principals", []))
        if product_statement is not None
        else set()
    )
    release_principals = [
        environment.get("ORCHESTRATE_PRODUCT_OWNER_PRINCIPAL", ""),
        environment.get("ORCHESTRATE_FINAL_VERIFIER_PRINCIPAL", ""),
        *sorted(authorized_labelers),
    ]
    if allowed_signers is None or not principals_have_distinct_keys(allowed_signers, release_principals):
        authorized_labelers = set()
    calibration_ok = current_human_calibration_report(
        root,
        calibration,
        allowed_signers,
        authorized_labelers,
        str(product_statement.get("principal")) if product_statement is not None else None,
    )
    checks.append(
        check(
            "aaa-human-calibration",
            calibration_ok,
            "ORC-041 and AAA completion require blind human calibration; QG-10 remains inactive while automatic graders have no release authority.",
        )
    )

    clients_ok = current_client_scope(root, supported_clients, nominated_artifact)
    checks.append(check("supported-client-scope", clients_ok, "Every declared client must have five PASS checks with tracked hash-bound artifacts; unlisted clients remain unsupported."))

    final_statement = current_final_attestation(
        root,
        environment,
        allowed_signers,
        head,
        artifact_sha256,
        product_statement_path,
        product_signature_path,
        product_statement,
    )
    final_statement_path = external_evidence_file(root, environment, "ORCHESTRATE_FINAL_VERIFIER_ATTESTATION")
    independently_approved = final_statement is not None
    checks.append(check("independent-approval", independently_approved, "A distinct verifier must provide a strictly later external signature over this exact HEAD, quality bar, skill, artifact, product statement, and product signature."))

    ci_sha = environment.get("GITHUB_SHA", "")
    ci_ok = environment.get("GITHUB_ACTIONS") == "true" and head_result.returncode == 0 and ci_sha == head
    checks.append(check("ci-provenance", ci_ok, "Release approval must run in GitHub Actions at the exact HEAD commit."))

    if [str(item["name"]) for item in checks] != list(REQUIRED_RELEASE_GATES):
        raise ValueError("release gate implementation diverges from the frozen quality bar")

    return {
        "passed": all(bool(item["passed"]) for item in checks),
        "release_approved": all(bool(item["passed"]) for item in checks),
        "version": version,
        "source_sha256": sha256(root / "SKILL.md"),
        "artifact_sha256": artifact_sha256,
        "fresh_artifact_sha256": fresh_artifact_sha256,
        "artifact": str(nominated_artifact),
        "head": head,
        "authority": {
            "signature_namespace": "orchestrate-release",
            "trust_anchor_sha256": sha256(allowed_signers) if allowed_signers is not None else None,
            "product_owner": {
                "principal": product_statement.get("principal"),
                "issued_at": product_statement.get("issued_at"),
                "statement_sha256": sha256(product_statement_path) if product_statement_path is not None else None,
            } if product_statement is not None else None,
            "independent_verifier": {
                "principal": final_statement.get("principal"),
                "issued_at": final_statement.get("issued_at"),
                "statement_sha256": sha256(final_statement_path) if final_statement_path is not None else None,
            } if final_statement is not None else None,
        },
        "checks": checks,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(args.root.resolve(), artifact=args.artifact)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["passed"] else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"validate_release: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
