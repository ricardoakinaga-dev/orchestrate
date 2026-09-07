#!/usr/bin/env python3
"""Validate and score Orchestrate behavioral evaluation predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


MODES = {"direct", "scout-assisted", "multi-workstream"}
AUTHORIZATIONS = {"read-only", "local-write", "approval-required"}
CATEGORIES = {"activation", "mode", "e2e", "security"}
LOCALES = {"en", "pt-BR"}
REQUIRED_COVERAGE_TAGS = {"negative", "edge", "adversarial", "long-context", "critical"}
REQUIRED_UNTRUSTED_SOURCE_TAGS = {"code", "documentation", "issue", "log", "tool-output"}
CASE_FIELDS = {"id", "locale", "category", "prompt", "expected", "rationale", "tags"}
EXPECTED_FIELDS = {"activate", "mode", "delegate", "authorization"}
PREDICTION_FIELDS = {"id", "run", "activate", "mode", "delegate", "authorization", "critical_violation", "rationale"}
CASE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{3}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = strict_json_loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: each line must be an object")
        records.append(value)
    return records


def load_thresholds(path: Path) -> dict[str, object]:
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("thresholds must be a JSON object")
    return value


def validate_cases(cases: Iterable[dict[str, object]], thresholds: dict[str, object], minimum_override: int | None = None) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    categories: set[str] = set()
    locales: set[str] = set()
    tags: set[str] = set()
    prompts: set[str] = set()
    case_list = list(cases)
    for index, case in enumerate(case_list, start=1):
        case_id = case.get("id")
        prefix = str(case_id or f"line-{index}")
        if set(case) != CASE_FIELDS:
            errors.append(f"{prefix}: case fields must be exactly {sorted(CASE_FIELDS)}")
        if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
            errors.append(f"{prefix}: id must match ^[A-Z][A-Z0-9]*-[0-9]{{3}}$")
        elif case_id in seen:
            errors.append(f"{prefix}: duplicate id")
        else:
            seen.add(case_id)
        locale = case.get("locale")
        category = case.get("category")
        if locale not in LOCALES:
            errors.append(f"{prefix}: invalid locale {locale!r}")
        else:
            locales.add(str(locale))
        if category not in CATEGORIES:
            errors.append(f"{prefix}: invalid category {category!r}")
        else:
            categories.add(str(category))
        prompt = case.get("prompt")
        if not isinstance(prompt, str) or len(prompt.strip()) < 8:
            errors.append(f"{prefix}: prompt is too short")
        elif " ".join(prompt.casefold().split()) in prompts:
            errors.append(f"{prefix}: duplicate normalized prompt")
        else:
            prompts.add(" ".join(prompt.casefold().split()))
        if not isinstance(case.get("rationale"), str) or len(str(case.get("rationale", "")).strip()) < 8:
            errors.append(f"{prefix}: rationale is too short")
        expected = case.get("expected")
        if not isinstance(expected, dict):
            errors.append(f"{prefix}: expected must be an object")
        else:
            if set(expected) != EXPECTED_FIELDS:
                errors.append(f"{prefix}: expected fields must be exactly {sorted(EXPECTED_FIELDS)}")
            if not isinstance(expected.get("activate"), bool):
                errors.append(f"{prefix}: expected.activate must be boolean")
            if expected.get("mode") not in MODES:
                errors.append(f"{prefix}: invalid expected.mode")
            if not isinstance(expected.get("delegate"), bool):
                errors.append(f"{prefix}: expected.delegate must be boolean")
            if expected.get("authorization") not in AUTHORIZATIONS:
                errors.append(f"{prefix}: invalid expected.authorization")
            if expected.get("delegate") and expected.get("mode") == "direct":
                errors.append(f"{prefix}: direct mode cannot delegate")
            if expected.get("activate") is False and (expected.get("mode") != "direct" or expected.get("delegate") is not False):
                errors.append(f"{prefix}: inactive cases must be direct and non-delegating")
        case_tags = case.get("tags")
        if not isinstance(case_tags, list) or not case_tags or not all(isinstance(tag, str) and tag for tag in case_tags):
            errors.append(f"{prefix}: tags must be a non-empty string array")
        else:
            if len(case_tags) != len(set(case_tags)):
                errors.append(f"{prefix}: tags must be unique")
            tags.update(case_tags)

    minimum = minimum_override if minimum_override is not None else int(thresholds.get("minimum_cases", 0))
    if len(case_list) < minimum:
        errors.append(f"dataset has {len(case_list)} cases; minimum is {minimum}")
    for required in thresholds.get("required_categories", []):
        if required not in categories:
            errors.append(f"missing required category {required}")
    for required in thresholds.get("required_locales", []):
        if required not in locales:
            errors.append(f"missing required locale {required}")
    for category in CATEGORIES:
        present_locales = {str(case["locale"]) for case in case_list if case.get("category") == category and case.get("locale") in LOCALES}
        if present_locales != LOCALES:
            errors.append(f"category {category} must include both locales")
    required_tags = set(REQUIRED_COVERAGE_TAGS)
    if minimum_override is None or minimum_override >= int(thresholds.get("minimum_cases", 0)):
        required_tags.update(REQUIRED_UNTRUSTED_SOURCE_TAGS)
    for required_tag in required_tags:
        if required_tag not in tags:
            errors.append(f"missing coverage tag {required_tag}")
    for case in case_list:
        case_tags = case.get("tags", [])
        if isinstance(case_tags, list) and "long-context" in case_tags and len(str(case.get("prompt", ""))) < 500:
            errors.append(f"{case.get('id')}: long-context prompt must contain at least 500 characters")
    return errors


def validate_predictions(predictions: Iterable[dict[str, object]], case_ids: set[str], expected_runs: int | None = None) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, int]] = set()
    runs_by_case: dict[str, set[int]] = defaultdict(set)
    for index, prediction in enumerate(predictions, start=1):
        prediction_id = prediction.get("id")
        run = prediction.get("run")
        prefix = str(prediction_id or f"line-{index}")
        if set(prediction) != PREDICTION_FIELDS:
            errors.append(f"{prefix}: prediction fields must be exactly {sorted(PREDICTION_FIELDS)}")
        if prediction_id not in case_ids:
            errors.append(f"{prefix}: unknown case id")
        if not isinstance(run, int) or run < 1:
            errors.append(f"{prefix}: run must be a positive integer")
        elif isinstance(prediction_id, str) and (prediction_id, run) in seen:
            errors.append(f"{prefix}: duplicate run {run}")
        elif isinstance(prediction_id, str):
            seen.add((prediction_id, run))
            runs_by_case[prediction_id].add(run)
        if not isinstance(prediction.get("activate"), bool):
            errors.append(f"{prefix}: activate must be boolean")
        if prediction.get("mode") not in MODES:
            errors.append(f"{prefix}: invalid mode")
        if not isinstance(prediction.get("delegate"), bool):
            errors.append(f"{prefix}: delegate must be boolean")
        if prediction.get("authorization") not in AUTHORIZATIONS:
            errors.append(f"{prefix}: invalid authorization")
        if prediction.get("mode") == "direct" and prediction.get("delegate") is True:
            errors.append(f"{prefix}: direct mode cannot delegate")
        if prediction.get("activate") is False and (prediction.get("mode") != "direct" or prediction.get("delegate") is not False):
            errors.append(f"{prefix}: inactive predictions must be direct and non-delegating")
        if not isinstance(prediction.get("critical_violation"), bool):
            errors.append(f"{prefix}: critical_violation must be boolean")
        if not isinstance(prediction.get("rationale"), str) or not str(prediction.get("rationale", "")).strip():
            errors.append(f"{prefix}: rationale is required")
    if expected_runs is not None:
        if not isinstance(expected_runs, int) or isinstance(expected_runs, bool) or expected_runs < 1:
            errors.append("expected_runs must be a positive integer")
        else:
            required = set(range(1, expected_runs + 1))
            for case_id in sorted(case_ids):
                if runs_by_case[case_id] != required:
                    errors.append(f"{case_id}: runs must be exactly {sorted(required)}; got {sorted(runs_by_case[case_id])}")
    return errors


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def score(cases: list[dict[str, object]], predictions: list[dict[str, object]], thresholds: dict[str, object], min_runs: int) -> dict[str, object]:
    by_id = {str(case["id"]): case for case in cases}
    runs_by_case: dict[str, set[int]] = defaultdict(set)
    for item in predictions:
        if isinstance(item.get("run"), int):
            runs_by_case[str(item["id"])].add(int(item["run"]))
    required_runs = set(range(1, min_runs + 1))
    coverage_errors = [
        f"{case_id} runs must equal {sorted(required_runs)}; got {sorted(runs_by_case[case_id])}"
        for case_id in by_id
        if runs_by_case[case_id] != required_runs
    ]

    correct = Counter()
    totals = Counter()
    false_positives = 0
    expected_negative = 0
    critical_violations = 0
    topology_violations = 0
    segments: dict[str, Counter[str]] = defaultdict(Counter)
    mode_confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for prediction in predictions:
        case = by_id.get(str(prediction["id"]))
        if case is None:
            continue
        expected = case["expected"]
        assert isinstance(expected, dict)
        mode_confusion[str(expected["mode"])][str(prediction["mode"])] += 1
        for field in ("activate", "mode", "delegate", "authorization"):
            totals[field] += 1
            if prediction[field] == expected[field]:
                correct[field] += 1
        if expected["activate"] is False:
            expected_negative += 1
            if prediction["activate"] is True:
                false_positives += 1
        if prediction["critical_violation"] is True:
            critical_violations += 1
        if (prediction["mode"] == "direct" and prediction["delegate"] is True) or (
            prediction["activate"] is False and (prediction["mode"] != "direct" or prediction["delegate"] is not False)
        ):
            topology_violations += 1
        segment_names = [f"locale:{case['locale']}", f"category:{case['category']}"]
        segment_names.extend(f"tag:{tag}" for tag in case.get("tags", []) if isinstance(tag, str))
        for segment_name in segment_names:
            segments[segment_name]["total"] += 1
            if all(prediction[field] == expected[field] for field in ("activate", "mode", "delegate", "authorization")) and prediction["critical_violation"] is False:
                segments[segment_name]["exact"] += 1

    metrics = {
        "activation_accuracy": ratio(correct["activate"], totals["activate"]),
        "false_positive_rate": ratio(false_positives, expected_negative),
        "mode_accuracy": ratio(correct["mode"], totals["mode"]),
        "delegation_accuracy": ratio(correct["delegate"], totals["delegate"]),
        "authorization_accuracy": ratio(correct["authorization"], totals["authorization"]),
        "critical_violations": critical_violations,
        "topology_violations": topology_violations,
    }
    checks = {
        "activation": metrics["activation_accuracy"] >= float(thresholds["activation_accuracy_min"]),
        "false_positive": metrics["false_positive_rate"] <= float(thresholds["false_positive_rate_max"]),
        "mode": metrics["mode_accuracy"] >= float(thresholds["mode_accuracy_min"]),
        "delegation": metrics["delegation_accuracy"] >= float(thresholds["delegation_accuracy_min"]),
        "authorization": metrics["authorization_accuracy"] >= float(thresholds["authorization_accuracy_min"]),
        "critical_violations": critical_violations <= int(thresholds["critical_violations_max"]),
        "topology": topology_violations == 0,
        "coverage": not coverage_errors,
    }
    return {
        "passed": all(checks.values()),
        "cases": len(cases),
        "predictions": len(predictions),
        "minimum_runs": min_runs,
        "checks": checks,
        "metrics": metrics,
        "coverage_errors": coverage_errors,
        "segments": {name: {"exact_accuracy": ratio(value["exact"], value["total"]), "samples": value["total"]} for name, value in sorted(segments.items())},
        "mode_confusion": {expected: dict(sorted(predicted.items())) for expected, predicted in sorted(mode_confusion.items())},
    }


def gold_predictions(cases: list[dict[str, object]], runs: int) -> list[dict[str, object]]:
    predictions: list[dict[str, object]] = []
    for case in cases:
        expected = case["expected"]
        assert isinstance(expected, dict)
        for run in range(1, runs + 1):
            predictions.append({"id": case["id"], "run": run, **expected, "critical_violation": False, "rationale": "Harness gold fixture."})
    return predictions


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "export", "score", "selftest"))
    parser.add_argument("--dataset", type=Path, default=root / "evals" / "cases.jsonl")
    parser.add_argument("--thresholds", type=Path, default=root / "config" / "eval-thresholds.json")
    parser.add_argument("--predictions", type=Path, nargs="+")
    parser.add_argument("--min-runs", type=int, default=1)
    parser.add_argument("--minimum-cases", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        cases = load_jsonl(args.dataset)
        thresholds = load_thresholds(args.thresholds)
        errors = validate_cases(cases, thresholds, args.minimum_cases)
        if errors:
            raise ValueError("\n".join(errors))
        if args.command == "validate":
            print(f"run_evals validate: PASS ({len(cases)} cases)")
            return 0
        if args.command == "export":
            if args.output is None:
                raise ValueError("--output is required for export")
            requests = [{"id": case["id"], "prompt": case["prompt"]} for case in cases]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests), encoding="utf-8")
            print(f"run_evals export: PASS ({len(requests)} blind requests -> {args.output})")
            return 0
        if args.command == "selftest":
            min_runs = int(thresholds["release_min_runs_per_case"])
            predictions = gold_predictions(cases, min_runs)
        else:
            if not args.predictions:
                raise ValueError("--predictions is required for score")
            min_runs = args.min_runs
            predictions = [item for path in args.predictions for item in load_jsonl(path)]
        prediction_errors = validate_predictions(predictions, {str(case["id"]) for case in cases}, min_runs)
        if prediction_errors:
            raise ValueError("\n".join(prediction_errors))
        report = score(cases, predictions, thresholds, min_runs)
        report["evidence_scope"] = "routing-classification-only"
        report["release_authority"] = False
        report["provenance"] = {
            "dataset": str(args.dataset),
            "dataset_sha256": sha256(args.dataset),
            "thresholds": str(args.thresholds),
            "thresholds_sha256": sha256(args.thresholds),
            "prediction_files": [
                {"path": str(path), "sha256": sha256(path)} for path in (args.predictions or [])
            ],
            "python": platform.python_version(),
            "platform": platform.platform(),
            "prediction_source": "gold-selftest" if args.command == "selftest" else "blind-evaluator-output",
        }
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["passed"] else 1
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"run_evals {args.command}: FAIL\n{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
