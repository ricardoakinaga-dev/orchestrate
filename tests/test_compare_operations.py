from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.compare_operations import compare, validate_runs


ROOT = Path(__file__).resolve().parents[1]


def sample() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for scenario, task_class in (("parallel-feature", "parallelizable"), ("coupled-parser", "coupled"), ("broad-review", "review")):
        for configuration in ("single", "orchestrate"):
            for run in range(1, 4):
                records.append({"scenario": scenario, "configuration": configuration, "run": run, "task_class": task_class, "status": "PASS", "quality_score": 1.0, "tokens": 1000 if configuration == "single" else 1200, "latency_ms": 1000 if configuration == "single" else 700, "agents": 0 if configuration == "single" else 3, "retries": 0, "rework": 0, "collisions": 0, "cost_usd": 1.0 if configuration == "single" else 1.2, "environment": "fixture-v1", "candidate_source_sha256": "d" * 64, "candidate_artifact_sha256": "e" * 64, "task_input_sha256": "a" * 64, "artifact_sha256": "b" * 64, "quality_evidence_sha256": "c" * 64, "measurement_source": "fixture", "owner_attestation": "test fixture only"})
    return records


class CompareOperationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.thresholds = json.loads((ROOT / "config" / "operational-thresholds.json").read_text(encoding="utf-8"))

    def test_paired_sample_passes(self) -> None:
        records = sample()
        self.assertEqual([], validate_runs(records, 3))
        self.assertTrue(compare(records, self.thresholds)["passed"])

    def test_fixture_measurements_are_not_release_evidence(self) -> None:
        records = sample()
        self.assertTrue(compare(records, self.thresholds)["passed"])
        self.assertTrue(all(record["measurement_source"] == "fixture" for record in records))

    def test_blocked_or_colliding_run_fails(self) -> None:
        records = sample()
        records[-1]["status"] = "BLOCKED"
        records[-1]["collisions"] = 1
        report = compare(records, self.thresholds)
        self.assertFalse(report["checks"]["complete"])
        self.assertFalse(report["checks"]["collisions"])

    def test_all_failed_runs_cannot_pass_by_matching_each_other(self) -> None:
        records = sample()
        for record in records:
            record["status"] = "FAIL"
        self.assertFalse(compare(records, self.thresholds)["passed"])

    def test_not_run_metrics_may_be_unknown_without_becoming_pass(self) -> None:
        records = sample()
        records[-1]["status"] = "NOT RUN"
        for field in ("quality_score", "tokens", "latency_ms", "agents", "retries", "rework", "collisions", "cost_usd"):
            records[-1][field] = None
        self.assertEqual([], validate_runs(records, 3))
        self.assertFalse(compare(records, self.thresholds)["passed"])

    def test_shifted_run_ids_are_not_treated_as_paired_repetitions(self) -> None:
        records = sample()
        for record in records:
            if record["configuration"] == "orchestrate":
                record["run"] += 10
        self.assertTrue(any("runs must be exactly" in error for error in validate_runs(records, 3)))

    def test_unrelated_classes_cannot_mask_parallel_quality_collapse(self) -> None:
        records = sample()
        for record in records:
            if record["task_class"] == "parallelizable" and record["configuration"] == "orchestrate":
                record["quality_score"] = 0.1
        report = compare(records, self.thresholds)
        self.assertFalse(report["checks"]["quality_noninferiority"])
        self.assertFalse(report["class_metrics"]["parallelizable"]["quality_noninferior"])

    def test_paired_runs_must_bind_same_task_input(self) -> None:
        records = sample()
        records[1]["task_input_sha256"] = "d" * 64
        self.assertTrue(any("same task input" in error for error in validate_runs(records, 3)))


if __name__ == "__main__":
    unittest.main()
