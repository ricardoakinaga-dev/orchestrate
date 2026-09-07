#!/usr/bin/env python3
"""Validate and compare paired single-agent and Orchestrate benchmark runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


CONFIGURATIONS = {"single", "orchestrate"}
TASK_CLASSES = {"parallelizable", "coupled", "review"}
STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT RUN"}
MEASUREMENT_SOURCES = {"codex-exec-jsonl", "codex-app-server", "fixture"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_regular_file(path: Path, root: Path) -> str | None:
    """Return a portable root-relative path only for a real, in-tree file."""
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return None
    if path.is_symlink() or not resolved.is_file():
        return None
    return relative.as_posix()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = strict_json_loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: each run must be an object")
        records.append(value)
    return records


def validate_runs(records: list[dict[str, object]], minimum_runs: int) -> list[str]:
    errors: list[str] = []
    expected = {
        "scenario", "configuration", "run", "task_class", "status", "quality_score", "tokens", "latency_ms",
        "agents", "retries", "rework", "collisions", "cost_usd", "environment", "task_input_sha256",
        "artifact_sha256", "quality_evidence_sha256", "candidate_source_sha256", "candidate_artifact_sha256",
        "measurement_source", "owner_attestation",
    }
    seen: set[tuple[str, str, int]] = set()
    run_sets: dict[tuple[str, str], set[int]] = defaultdict(set)
    scenario_class: dict[str, str] = {}
    scenario_environment: dict[str, str] = {}
    scenario_input: dict[str, str] = {}
    scenario_source: dict[str, str] = {}
    for index, record in enumerate(records, start=1):
        prefix = str(record.get("scenario") or f"line-{index}")
        if set(record) != expected:
            errors.append(f"{prefix}: fields must be exactly {sorted(expected)}")
            continue
        scenario = record["scenario"]
        configuration = record["configuration"]
        run = record["run"]
        task_class = record["task_class"]
        status = record["status"]
        environment = record["environment"]
        if not isinstance(scenario, str) or not scenario.strip() or configuration not in CONFIGURATIONS or task_class not in TASK_CLASSES or status not in STATUSES:
            errors.append(f"{prefix}: invalid identity/class/status")
            continue
        if not isinstance(run, int) or run < 1:
            errors.append(f"{prefix}: run must be a positive integer")
            continue
        key = (scenario, str(configuration), run)
        if key in seen:
            errors.append(f"{prefix}: duplicate configuration/run")
        seen.add(key)
        run_sets[(scenario, str(configuration))].add(run)
        if scenario in scenario_class and scenario_class[scenario] != task_class:
            errors.append(f"{prefix}: task_class differs across paired runs")
        scenario_class[scenario] = str(task_class)
        if not isinstance(environment, str) or not environment.strip():
            errors.append(f"{prefix}: environment is required")
        elif scenario in scenario_environment and scenario_environment[scenario] != environment:
            errors.append(f"{prefix}: paired runs must use the same environment")
        else:
            scenario_environment[scenario] = environment
        task_input = record["task_input_sha256"]
        if not isinstance(task_input, str) or not SHA256_RE.fullmatch(task_input):
            errors.append(f"{prefix}: task_input_sha256 must be a lowercase SHA-256 digest")
        elif scenario in scenario_input and scenario_input[scenario] != task_input:
            errors.append(f"{prefix}: paired runs must bind the same task input")
        else:
            scenario_input[scenario] = task_input
        for field in ("candidate_source_sha256", "candidate_artifact_sha256", "artifact_sha256", "quality_evidence_sha256"):
            value = record[field]
            if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
                errors.append(f"{prefix}: {field} must be a lowercase SHA-256 digest")
        measurement_source = record["measurement_source"]
        if measurement_source not in MEASUREMENT_SOURCES:
            errors.append(f"{prefix}: invalid measurement_source")
        elif scenario in scenario_source and scenario_source[scenario] != measurement_source:
            errors.append(f"{prefix}: paired runs must use the same measurement source")
        else:
            scenario_source[scenario] = str(measurement_source)
        if not isinstance(record["owner_attestation"], str) or not str(record["owner_attestation"]).strip():
            errors.append(f"{prefix}: owner_attestation is required")
        incomplete = status in {"BLOCKED", "NOT RUN"}
        for field in ("tokens", "latency_ms", "agents", "retries", "rework", "collisions"):
            value = record[field]
            if value is None and incomplete:
                continue
            if not isinstance(value, int) or value < 0:
                errors.append(f"{prefix}: {field} must be a non-negative integer when available")
        for field in ("quality_score", "cost_usd"):
            value = record[field]
            if value is None and incomplete:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                errors.append(f"{prefix}: {field} must be a non-negative number when available")
        if isinstance(record["quality_score"], (int, float)) and record["quality_score"] > 1:
            errors.append(f"{prefix}: quality_score must not exceed 1")
    scenarios = {scenario for scenario, _configuration in run_sets}
    required_runs = set(range(1, minimum_runs + 1))
    for scenario in scenarios:
        for configuration in CONFIGURATIONS:
            observed = run_sets[(scenario, configuration)]
            if observed != required_runs:
                errors.append(f"{scenario}: {configuration} runs must be exactly {sorted(required_runs)}; got {sorted(observed)}")
        if run_sets[(scenario, "single")] != run_sets[(scenario, "orchestrate")]:
            errors.append(f"{scenario}: single and orchestrate run IDs must be paired exactly")
    represented_classes = set(scenario_class.values())
    missing_classes = TASK_CLASSES - represented_classes
    if missing_classes:
        errors.append(f"benchmark is missing task classes: {sorted(missing_classes)}")
    return errors


def median(records: list[dict[str, object]], field: str) -> float:
    return round(float(statistics.median(float(record[field]) for record in records)), 6)


def median_absolute_deviation(records: list[dict[str, object]], field: str) -> float:
    values = [float(record[field]) for record in records]
    center = statistics.median(values)
    return round(float(statistics.median(abs(value - center) for value in values)), 6)


def compare(records: list[dict[str, object]], thresholds: dict[str, object]) -> dict[str, object]:
    if any(record["status"] in {"BLOCKED", "NOT RUN"} for record in records):
        collision_values = [record["collisions"] for record in records]
        return {
            "passed": False,
            "checks": {
                "complete": False,
                "collisions": all(isinstance(value, int) for value in collision_values)
                and sum(int(value) for value in collision_values) <= int(thresholds["max_collisions"]),
            },
            "metrics": {},
            "parallel_latency_improvement": None,
            "token_ratio": None,
            "cost_ratio": None,
            "runs": len(records),
        }
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        groups[str(record["configuration"])].append(record)
    metrics: dict[str, dict[str, float]] = {}
    for configuration in sorted(CONFIGURATIONS):
        items = groups[configuration]
        metrics[configuration] = {
            "success_rate": round(sum(item["status"] == "PASS" for item in items) / len(items), 6),
            "quality_median": median(items, "quality_score"),
            "tokens_median": median(items, "tokens"),
            "latency_ms_median": median(items, "latency_ms"),
            "latency_ms_mad": median_absolute_deviation(items, "latency_ms"),
            "agents_median": median(items, "agents"),
            "retries_total": float(sum(int(item["retries"]) for item in items)),
            "rework_total": float(sum(int(item["rework"]) for item in items)),
            "collisions_total": float(sum(int(item["collisions"]) for item in items)),
            "cost_usd_median": median(items, "cost_usd"),
            "tokens_mad": median_absolute_deviation(items, "tokens"),
        }
    parallel = {configuration: [item for item in groups[configuration] if item["task_class"] == "parallelizable"] for configuration in CONFIGURATIONS}
    single_latency = median(parallel["single"], "latency_ms") if parallel["single"] else 0.0
    orchestrate_latency = median(parallel["orchestrate"], "latency_ms") if parallel["orchestrate"] else 0.0
    latency_improvement = round((single_latency - orchestrate_latency) / single_latency, 6) if single_latency else 0.0
    single = metrics["single"]
    orchestrate = metrics["orchestrate"]
    def safe_ratio(numerator: float, denominator: float) -> float:
        if denominator:
            return round(numerator / denominator, 6)
        return 1.0 if numerator == 0 else float("inf")

    token_ratio = safe_ratio(orchestrate["tokens_median"], single["tokens_median"])
    cost_ratio = safe_ratio(orchestrate["cost_usd_median"], single["cost_usd_median"])
    by_pair: dict[tuple[str, int], dict[str, dict[str, object]]] = defaultdict(dict)
    for item in records:
        by_pair[(str(item["scenario"]), int(item["run"]))][str(item["configuration"])] = item
    pair_results: list[dict[str, object]] = []
    for (scenario, run), pair in sorted(by_pair.items()):
        if set(pair) != CONFIGURATIONS:
            continue
        base = pair["single"]
        candidate = pair["orchestrate"]
        pair_results.append(
            {
                "scenario": scenario,
                "run": run,
                "task_class": base["task_class"],
                "success_noninferior": base["status"] != "PASS" or candidate["status"] == "PASS",
                "quality_noninferior": float(candidate["quality_score"]) + float(thresholds["quality_noninferiority_tolerance"]) >= float(base["quality_score"]),
                "token_ratio": safe_ratio(float(candidate["tokens"]), float(base["tokens"])),
                "cost_ratio": safe_ratio(float(candidate["cost_usd"]), float(base["cost_usd"])),
            }
        )
    class_metrics: dict[str, dict[str, object]] = {}
    for task_class in sorted(TASK_CLASSES):
        class_single = [item for item in groups["single"] if item["task_class"] == task_class]
        class_orchestrate = [item for item in groups["orchestrate"] if item["task_class"] == task_class]
        class_metrics[task_class] = {
            "single_quality_median": median(class_single, "quality_score"),
            "orchestrate_quality_median": median(class_orchestrate, "quality_score"),
            "quality_noninferior": median(class_orchestrate, "quality_score") + float(thresholds["quality_noninferiority_tolerance"]) >= median(class_single, "quality_score"),
            "single_success_rate": round(sum(item["status"] == "PASS" for item in class_single) / len(class_single), 6),
            "orchestrate_success_rate": round(sum(item["status"] == "PASS" for item in class_orchestrate) / len(class_orchestrate), 6),
        }
    parallel_scenario_checks: dict[str, bool] = {}
    for scenario in sorted({str(item["scenario"]) for item in parallel["single"]}):
        base = [item for item in parallel["single"] if item["scenario"] == scenario]
        candidate = [item for item in parallel["orchestrate"] if item["scenario"] == scenario]
        improvement = (median(base, "latency_ms") - median(candidate, "latency_ms")) / median(base, "latency_ms") if median(base, "latency_ms") else 0.0
        parallel_scenario_checks[scenario] = improvement >= float(thresholds["parallel_latency_improvement_min"])
    checks = {
        "success_noninferiority": orchestrate["success_rate"] >= single["success_rate"] and all(item["success_noninferior"] for item in pair_results),
        "quality_noninferiority": all(bool(item["quality_noninferior"]) for item in pair_results) and all(bool(item["quality_noninferior"]) for item in class_metrics.values()),
        "parallel_latency": latency_improvement >= float(thresholds["parallel_latency_improvement_min"]) and all(parallel_scenario_checks.values()),
        "tokens": token_ratio <= float(thresholds["max_token_ratio"]) and all(float(item["token_ratio"]) <= float(thresholds["max_token_ratio"]) for item in pair_results),
        "cost": cost_ratio <= float(thresholds["max_cost_ratio"]) and all(float(item["cost_ratio"]) <= float(thresholds["max_cost_ratio"]) for item in pair_results),
        "agents": max(int(item["agents"]) for item in groups["orchestrate"]) <= int(thresholds["max_agents"]),
        "retries": max(int(item["retries"]) for item in records) <= int(thresholds["max_retries"]),
        "collisions": sum(int(item["collisions"]) for item in records) <= int(thresholds["max_collisions"]),
        "complete": all(item["status"] == "PASS" for item in records),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": metrics,
        "class_metrics": class_metrics,
        "pair_results": pair_results,
        "parallel_scenario_checks": parallel_scenario_checks,
        "parallel_latency_improvement": latency_improvement,
        "token_ratio": token_ratio,
        "cost_ratio": cost_ratio,
        "runs": len(records),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path)
    parser.add_argument("--thresholds", type=Path, default=root / "config" / "operational-thresholds.json")
    parser.add_argument(
        "--artifact",
        type=Path,
        help="exact plugin archive exercised by non-fixture runs; required for release eligibility",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        records = load_jsonl(args.runs)
        thresholds = strict_json_loads(args.thresholds.read_text(encoding="utf-8"))
        if not isinstance(thresholds, dict):
            raise ValueError("operational thresholds must be a JSON object")
        errors = validate_runs(records, int(thresholds["minimum_runs_per_configuration"]))
        if errors:
            raise ValueError("\n".join(errors))
        report = compare(records, thresholds)
        runs_relative = relative_regular_file(args.runs, root)
        thresholds_relative = relative_regular_file(args.thresholds, root)
        artifact = args.artifact.resolve() if args.artifact is not None else None
        artifact_valid = artifact is not None and artifact.is_file() and not artifact.is_symlink()
        artifact_digest = sha256(artifact) if artifact_valid else None
        source_digest = sha256(root / "SKILL.md")
        candidate_bound = bool(records) and all(
            record["candidate_source_sha256"] == source_digest
            and record["candidate_artifact_sha256"] == artifact_digest
            for record in records
        )
        report["evidence_scope"] = "paired-task-execution"
        report["release_eligible_measurements"] = (
            artifact_valid
            and runs_relative is not None
            and thresholds_relative == "config/operational-thresholds.json"
            and all(record["measurement_source"] != "fixture" for record in records)
            and candidate_bound
        )
        report["source_sha256"] = source_digest
        report["artifact_sha256"] = artifact_digest
        report["threshold_approval"] = thresholds.get("approval_status")
        report["provenance"] = {
            "runs": runs_relative,
            "runs_sha256": sha256(args.runs),
            "thresholds": thresholds_relative,
            "thresholds_sha256": sha256(args.thresholds),
            "artifact": str(artifact) if artifact is not None else None,
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
        print(f"compare_operations: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
