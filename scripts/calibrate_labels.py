#!/usr/bin/env python3
"""Measure blind human agreement and grader agreement for routing labels."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import platform
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
    from scripts.run_evals import AUTHORIZATIONS, MODES, load_jsonl, validate_predictions
    from scripts.signed_attestation import allowed_signer_keys, external_trust_anchor, load_signed_statement
except ModuleNotFoundError:  # Direct execution from scripts/.
    from json_strict import loads as strict_json_loads
    from run_evals import AUTHORIZATIONS, MODES, load_jsonl, validate_predictions
    from signed_attestation import allowed_signer_keys, external_trust_anchor, load_signed_statement


FIELDS = ("activate", "mode", "delegate", "authorization")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NON_HUMAN_ID_RE = re.compile(r"(?:^|[-_. ])(?:agent|bot|gpt|model|llm|claude|gemini|codex)(?:$|[-_. 0-9])", re.IGNORECASE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_regular_file(path: Path, root: Path) -> str | None:
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return None
    current = root.resolve()
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None
    if not resolved.is_file():
        return None
    return relative.as_posix()


def label_tuple(record: dict[str, object]) -> tuple[object, ...]:
    return tuple(record[field] for field in FIELDS)


def validate_labeler_registry(
    data: object,
    root: Path,
    allowed_signers: Path | None = None,
    authorized_principals: set[str] | None = None,
    verifying_principal: str | None = None,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    verified: dict[str, str] = {}
    if not isinstance(data, dict) or set(data) != {"schema_version", "labelers"} or data.get("schema_version") != 2:
        return {}, ["labeler registry root/schema is invalid"]
    if allowed_signers is None or authorized_principals is None or not verifying_principal:
        return {}, ["labeler registry requires an external trust anchor, product-owner-authorized principals, and verifying principal"]
    signer_keys = allowed_signer_keys(allowed_signers)
    if signer_keys is None:
        return {}, ["labeler registry trust anchor has an invalid signer profile"]
    used_keys: set[str] = set()
    labelers = data.get("labelers")
    if not isinstance(labelers, list) or len(labelers) < 2:
        return {}, ["labeler registry requires at least two entries"]
    for index, item in enumerate(labelers, start=1):
        prefix = f"labeler-{index}"
        expected = {
            "id", "identity_type", "verified_by", "verification_method", "principal",
            "attestation_path", "attestation_sha256", "signature_path", "signature_sha256",
        }
        if not isinstance(item, dict) or set(item) != expected:
            errors.append(f"{prefix}: registry fields must be exactly {sorted(expected)}")
            continue
        labeler = item.get("id")
        if not isinstance(labeler, str) or not labeler.strip() or NON_HUMAN_ID_RE.search(labeler):
            errors.append(f"{prefix}: id is empty or self-identifies as a non-human evaluator")
            continue
        if item.get("identity_type") != "human":
            errors.append(f"{labeler}: identity_type must be human")
        if item.get("verification_method") != "signed-human-attestation":
            errors.append(f"{labeler}: verification_method must be signed-human-attestation")
        verifier = item.get("verified_by")
        if not isinstance(verifier, str) or not verifier.strip() or verifier == labeler or verifier != verifying_principal:
            errors.append(f"{labeler}: verified_by must identify the authorizing product owner")
        principal = item.get("principal")
        if not isinstance(principal, str) or not principal.strip() or principal not in authorized_principals:
            errors.append(f"{labeler}: principal is not authorized by the product owner")
            continue
        signer_key = signer_keys.get(principal)
        if signer_key is None or signer_key in used_keys:
            errors.append(f"{labeler}: each human labeler requires a distinct authorized signing key")
            continue
        used_keys.add(signer_key)
        path_value = item.get("attestation_path")
        digest = item.get("attestation_sha256")
        signature_value = item.get("signature_path")
        signature_digest = item.get("signature_sha256")
        if (
            not isinstance(path_value, str) or not path_value.strip()
            or not isinstance(digest, str) or not SHA256_RE.fullmatch(digest)
            or not isinstance(signature_value, str) or not signature_value.strip()
            or not isinstance(signature_digest, str) or not SHA256_RE.fullmatch(signature_digest)
        ):
            errors.append(f"{labeler}: attestation/signature path or digest is invalid")
            continue
        unresolved = root / path_value
        unresolved_signature = root / signature_value
        relative_attestation = relative_regular_file(unresolved, root)
        relative_signature = relative_regular_file(unresolved_signature, root)
        if (
            relative_attestation is None
            or relative_signature is None
            or sha256(unresolved) != digest
            or sha256(unresolved_signature) != signature_digest
        ):
            errors.append(f"{labeler}: attestation/signature is missing, unsafe, or has the wrong digest")
            continue
        statement = load_signed_statement(unresolved, unresolved_signature, allowed_signers, principal, now=now)
        statement_fields = {"schema_version", "role", "principal", "issued_at", "labeler_id", "identity_type", "verified_by"}
        if (
            statement is None
            or set(statement) != statement_fields
            or statement.get("schema_version") != 1
            or statement.get("role") != "human-labeler"
            or statement.get("labeler_id") != labeler
            or statement.get("identity_type") != "human"
            or statement.get("verified_by") != verifier
        ):
            errors.append(f"{labeler}: signed human attestation is invalid or does not match the registry")
            continue
        if labeler in verified:
            errors.append(f"{labeler}: duplicate registry identity")
        verified[labeler] = digest
    return verified, errors


def validate_labels(
    records: list[dict[str, object]],
    case_ids: set[str],
    minimum_labelers: int = 2,
    verified_labelers: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    verified_labelers = verified_labelers or {}
    for index, record in enumerate(records, start=1):
        prefix = str(record.get("id") or f"line-{index}")
        expected = {"id", "labeler", "attestation_sha256", "activate", "mode", "delegate", "authorization", "rationale"}
        if set(record) != expected:
            errors.append(f"{prefix}: labels require exact fields {sorted(expected)}")
            continue
        if record["id"] not in case_ids or not isinstance(record["labeler"], str) or not str(record["labeler"]).strip():
            errors.append(f"{prefix}: unknown id or empty labeler")
        labeler = str(record["labeler"])
        if NON_HUMAN_ID_RE.search(labeler):
            errors.append(f"{prefix}: labeler self-identifies as an agent/model")
        if verified_labelers.get(labeler) != record.get("attestation_sha256"):
            errors.append(f"{prefix}: labeler is not bound to a verified human attestation")
        key = (str(record["id"]), str(record["labeler"]))
        if key in seen:
            errors.append(f"{prefix}: duplicate labeler/case")
        seen.add(key)
        if not isinstance(record["activate"], bool) or record["mode"] not in MODES or not isinstance(record["delegate"], bool) or record["authorization"] not in AUTHORIZATIONS:
            errors.append(f"{prefix}: invalid routing label")
        if record["mode"] == "direct" and record["delegate"] is True:
            errors.append(f"{prefix}: direct mode cannot delegate")
        if record["activate"] is False and (record["mode"] != "direct" or record["delegate"] is not False):
            errors.append(f"{prefix}: inactive labels must be direct and non-delegating")
        if not isinstance(record["rationale"], str) or not str(record["rationale"]).strip():
            errors.append(f"{prefix}: rationale is required")
    labels_by_case: dict[str, set[str]] = defaultdict(set)
    for record in records:
        case_id = record.get("id")
        labeler = record.get("labeler")
        if isinstance(case_id, str) and case_id in case_ids and isinstance(labeler, str) and labeler.strip():
            labels_by_case[case_id].add(labeler)
    for case_id in sorted(case_ids):
        count = len(labels_by_case[case_id])
        if count < minimum_labelers:
            errors.append(f"{case_id}: has {count} independent labelers; requires {minimum_labelers}")
    return errors


def exact_agreement(left: dict[str, dict[str, object]], right: dict[str, dict[str, object]]) -> float:
    shared = sorted(set(left) & set(right))
    return round(sum(label_tuple(left[item]) == label_tuple(right[item]) for item in shared) / len(shared), 6) if shared else 0.0


def calibrate(labels: list[dict[str, object]], predictions: list[dict[str, object]], thresholds: dict[str, object]) -> dict[str, object]:
    by_labeler: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    by_case: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in labels:
        by_labeler[str(record["labeler"])][str(record["id"])] = record
        by_case[str(record["id"])].append(record)
    pairwise = [exact_agreement(by_labeler[left], by_labeler[right]) for left, right in itertools.combinations(sorted(by_labeler), 2)]
    consensus: dict[str, tuple[object, ...]] = {}
    unresolved: list[str] = []
    for case_id, records in by_case.items():
        counts = Counter(label_tuple(record) for record in records)
        best, votes = counts.most_common(1)[0]
        if votes <= len(records) / 2:
            unresolved.append(case_id)
        else:
            consensus[case_id] = best
    comparable = [record for record in predictions if str(record.get("id")) in consensus]
    predictions_by_case: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in comparable:
        predictions_by_case[str(record["id"])].append(record)
    per_case_agreement = {
        case_id: round(sum(label_tuple(record) == consensus[case_id] for record in records) / len(records), 6)
        for case_id, records in predictions_by_case.items()
    }
    grader_agreement = round(sum(per_case_agreement.values()) / len(per_case_agreement), 6) if per_case_agreement else 0.0
    human_agreement = round(sum(pairwise) / len(pairwise), 6) if pairwise else 0.0
    expected_prediction_cases = set(consensus)
    observed_prediction_cases = {str(record.get("id")) for record in predictions if str(record.get("id")) in consensus}
    run_sets = {
        case_id: {record.get("run") for record in records}
        for case_id, records in predictions_by_case.items()
    }
    uniform_runs = bool(run_sets) and len({tuple(sorted(int(run) for run in runs if isinstance(run, int))) for runs in run_sets.values()}) == 1
    checks = {
        "multiple_humans": len(by_labeler) >= 2,
        "complete_consensus": not unresolved and bool(consensus),
        "prediction_coverage": observed_prediction_cases == expected_prediction_cases,
        "uniform_prediction_runs": uniform_runs,
        "human_agreement": human_agreement >= float(thresholds["human_pairwise_agreement_min"]),
        "grader_agreement": grader_agreement >= float(thresholds["grader_human_agreement_min"]),
    }
    return {"passed": all(checks.values()), "checks": checks, "labelers": sorted(by_labeler), "human_pairwise_agreement": human_agreement, "grader_human_agreement": grader_agreement, "per_case_grader_agreement": dict(sorted(per_case_agreement.items())), "consensus_cases": len(consensus), "unresolved_cases": sorted(unresolved), "prediction_samples": len(comparable)}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, nargs="+", required=True)
    parser.add_argument("--labeler-registry", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, nargs="+", required=True)
    parser.add_argument("--dataset", type=Path, default=root / "evals" / "cases.jsonl")
    parser.add_argument("--thresholds", type=Path, default=root / "config" / "eval-thresholds.json")
    parser.add_argument("--allowed-signers", type=Path, required=True)
    parser.add_argument("--allowed-signers-sha256", required=True)
    parser.add_argument("--authorized-principal", action="append", required=True)
    parser.add_argument("--verifying-principal", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        cases = load_jsonl(args.dataset)
        labels = [record for path in args.labels for record in load_jsonl(path)]
        predictions = [record for path in args.predictions for record in load_jsonl(path)]
        registry = strict_json_loads(args.labeler_registry.read_text(encoding="utf-8"))
        trust_environment = {
            "ORCHESTRATE_ALLOWED_SIGNERS": str(args.allowed_signers),
            "ORCHESTRATE_ALLOWED_SIGNERS_SHA256": args.allowed_signers_sha256,
        }
        allowed_signers = external_trust_anchor(root, trust_environment)
        if allowed_signers is None:
            raise ValueError("allowed signers must be a hash-bound regular file outside the repository")
        verified_labelers, registry_errors = validate_labeler_registry(
            registry,
            args.labeler_registry.parent,
            allowed_signers,
            set(args.authorized_principal),
            args.verifying_principal,
        )
        case_ids = {str(case["id"]) for case in cases}
        prediction_errors = validate_predictions(predictions, case_ids)
        errors = [*registry_errors, *validate_labels(labels, case_ids, verified_labelers=verified_labelers), *prediction_errors]
        if errors:
            raise ValueError("\n".join(errors))
        thresholds = strict_json_loads(args.thresholds.read_text(encoding="utf-8"))
        if not isinstance(thresholds, dict):
            raise ValueError("thresholds must be a JSON object")
        report = calibrate(labels, predictions, thresholds)
        dataset_relative = relative_regular_file(args.dataset, root)
        labels_relative = [relative_regular_file(path, root) for path in args.labels]
        registry_relative = relative_regular_file(args.labeler_registry, root)
        predictions_relative = [relative_regular_file(path, root) for path in args.predictions]
        thresholds_relative = relative_regular_file(args.thresholds, root)
        report["evidence_scope"] = "blind-human-routing-calibration"
        report["release_eligible_measurements"] = (
            dataset_relative == "evals/cases.jsonl"
            and thresholds_relative == "config/eval-thresholds.json"
            and registry_relative is not None
            and all(path is not None for path in labels_relative)
            and all(path is not None for path in predictions_relative)
        )
        report["provenance"] = {
            "dataset": dataset_relative,
            "dataset_sha256": sha256(args.dataset),
            "label_files": [{"path": relative, "sha256": sha256(path)} for path, relative in zip(args.labels, labels_relative)],
            "labeler_registry": {"path": registry_relative, "sha256": sha256(args.labeler_registry)},
            "prediction_files": [{"path": relative, "sha256": sha256(path)} for path, relative in zip(args.predictions, predictions_relative)],
            "thresholds": thresholds_relative,
            "thresholds_sha256": sha256(args.thresholds),
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["passed"] else 1
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"calibrate_labels: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
