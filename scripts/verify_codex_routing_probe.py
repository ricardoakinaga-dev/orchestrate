#!/usr/bin/env python3
"""Recompute routing-v3 predictions and score from bound Codex JSONL sessions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
    from scripts.run_codex_routing_probe import build_prompt, parse_session
    from scripts.run_codex_runtime_probe import charged_tokens, sha256
    from scripts.run_evals import load_jsonl, load_thresholds, score
    from scripts.validate_routing_receipt import validate as validate_receipt
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads
    from run_codex_routing_probe import build_prompt, parse_session
    from run_codex_runtime_probe import charged_tokens, sha256
    from run_evals import load_jsonl, load_thresholds, score
    from validate_routing_receipt import validate as validate_receipt


def load_json(path: Path) -> dict[str, object]:
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def bound(root: Path, descriptor: object) -> Path:
    if not isinstance(descriptor, dict) or set(descriptor) != {"path", "sha256"}:
        raise ValueError("evidence descriptor needs exactly path and sha256")
    relative = descriptor.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("evidence path must be repository-relative")
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
        raise ValueError(f"evidence path escapes repository: {relative}") from exc
    if not resolved.is_file() or descriptor.get("sha256") != sha256(resolved):
        raise ValueError(f"evidence digest mismatch: {relative}")
    return resolved


def verify(root: Path) -> dict[str, object]:
    root = root.resolve(strict=True)
    receipt_path = root / "evals" / "evidence" / "routing-v3" / "receipt.json"
    receipt = load_json(receipt_path)
    receipt_errors = validate_receipt(receipt, root)
    if receipt_errors:
        raise ValueError("routing receipt failed: " + "; ".join(receipt_errors))
    evaluators = receipt.get("evaluators")
    if not isinstance(evaluators, list):
        raise ValueError("routing receipt has no evaluators")
    case_ids = [str(case["id"]) for case in load_jsonl(root / "evals" / "cases.jsonl")]
    all_predictions: list[dict[str, object]] = []
    evidence_paths = {
        "evals/evidence/routing-v3/receipt.json",
        "evals/evidence/routing-v3/source-snapshot.json",
        "evals/reports/routing-v3.json",
    }
    threads: list[str] = []
    tokens: list[int] = []
    for evaluator in sorted(evaluators, key=lambda value: int(value["run"]) if isinstance(value, dict) else 0):
        if not isinstance(evaluator, dict):
            raise ValueError("invalid evaluator receipt")
        run = evaluator.get("run")
        if not isinstance(run, int):
            raise ValueError("evaluator run is not an integer")
        prompt_path = bound(root, evaluator.get("prompt"))
        if prompt_path.read_text(encoding="utf-8") != build_prompt(root, run):
            raise ValueError(f"run {run}: stored prompt does not reproduce from current blind inputs")
        session_path = bound(root, evaluator.get("session_rollout"))
        thread_id, predictions, usage = parse_session(session_path.read_text(encoding="utf-8"), run, case_ids)
        if thread_id != evaluator.get("thread_id") or charged_tokens(usage) != evaluator.get("tokens_used"):
            raise ValueError(f"run {run}: session identity or token count mismatch")
        output_path = bound(root, evaluator.get("output"))
        stored_predictions = load_jsonl(output_path)
        if predictions != stored_predictions:
            raise ValueError(f"run {run}: predictions do not reproduce from raw session")
        invocation_path = bound(root, evaluator.get("invocation"))
        invocation = load_json(invocation_path)
        expected_invocation = {
            "schema_version": 1,
            "client": "codex-cli",
            "client_version": evaluator.get("cli_version"),
            "model": evaluator.get("model"),
            "reasoning_effort": evaluator.get("reasoning_effort"),
            "ephemeral": True,
            "ignore_user_config": True,
            "ignore_rules": True,
            "sandbox": "read-only",
            "shell_environment_inherit": "none",
            "output_schema_sha256": sha256(root / "schemas" / "codex-routing-probe-output.schema.json"),
            "exit_code": 0,
            "stderr": "Reading additional input from stdin...\n",
            "usage": usage,
            "charged_tokens": charged_tokens(usage),
        }
        if invocation != expected_invocation:
            raise ValueError(f"run {run}: invocation receipt does not reproduce")
        for field in ("prompt", "session_rollout", "output", "invocation"):
            descriptor = evaluator[field]
            assert isinstance(descriptor, dict)
            evidence_paths.add(str(descriptor["path"]))
        threads.append(thread_id)
        tokens.append(charged_tokens(usage))
        all_predictions.extend(predictions)
    if len(set(threads)) != 3:
        raise ValueError("routing sessions do not have three distinct thread IDs")
    cases = load_jsonl(root / "evals" / "cases.jsonl")
    thresholds = load_thresholds(root / "config" / "eval-thresholds.json")
    recomputed = score(cases, all_predictions, thresholds, 3)
    report = load_json(root / "evals" / "reports" / "routing-v3.json")
    if any(report.get(key) != value for key, value in recomputed.items()):
        raise ValueError("routing report does not reproduce from raw sessions")
    provenance = report.get("provenance")
    if (
        report.get("evidence_scope") != "routing-classification-only"
        or report.get("release_authority") is not False
        or not isinstance(provenance, dict)
        or provenance.get("dataset") != "evals/cases.jsonl"
        or provenance.get("dataset_sha256") != sha256(root / "evals" / "cases.jsonl")
        or provenance.get("thresholds") != "config/eval-thresholds.json"
        or provenance.get("thresholds_sha256") != sha256(root / "config" / "eval-thresholds.json")
        or provenance.get("prediction_source") != "blind-evaluator-output"
    ):
        raise ValueError("routing report provenance is invalid")
    expected_prediction_descriptors = [evaluator["output"] for evaluator in sorted(evaluators, key=lambda value: int(value["run"]))]
    if provenance.get("prediction_files") != expected_prediction_descriptors:
        raise ValueError("routing report prediction descriptors differ from receipt")
    return {
        "passed": bool(report.get("passed")),
        "cases": len(cases),
        "predictions": len(all_predictions),
        "threads": threads,
        "tokens_used": tokens,
        "evidence_paths": sorted(evidence_paths),
        "report_sha256": sha256(root / "evals" / "reports" / "routing-v3.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = verify(args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, KeyError, AssertionError, json.JSONDecodeError) as exc:
        print(f"verify_codex_routing_probe: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
