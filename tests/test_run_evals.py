from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_evals import gold_predictions, load_jsonl, score, validate_cases, validate_predictions


ROOT = Path(__file__).resolve().parents[1]


class EvalHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_jsonl(ROOT / "evals" / "cases.jsonl")
        cls.thresholds = json.loads((ROOT / "config" / "eval-thresholds.json").read_text(encoding="utf-8"))

    def test_dataset_contract_and_coverage(self) -> None:
        self.assertEqual([], validate_cases(self.cases, self.thresholds))
        self.assertEqual(44, len(self.cases))

    def test_mode_boundaries_include_small_multifile_and_large_coupled(self) -> None:
        tags = {tag for case in self.cases for tag in case["tags"]}
        self.assertTrue({"small-multifile", "large-coupled"}.issubset(tags))

    def test_long_context_tag_requires_substantial_context(self) -> None:
        cases = [dict(case) for case in self.cases]
        tagged = next(case for case in cases if "long-context" in case["tags"])
        tagged["prompt"] = "Short context"
        errors = validate_cases(cases, self.thresholds)
        self.assertTrue(any("long-context prompt" in error for error in errors))

    def test_gold_predictions_pass_three_runs(self) -> None:
        predictions = gold_predictions(self.cases, 3)
        self.assertEqual([], validate_predictions(predictions, {str(case["id"]) for case in self.cases}))
        report = score(self.cases, predictions, self.thresholds, 3)
        self.assertTrue(report["passed"])
        self.assertEqual(0, report["metrics"]["critical_violations"])

    def test_known_bad_prediction_fails(self) -> None:
        predictions = gold_predictions(self.cases, 1)
        predictions[0]["critical_violation"] = True
        predictions[0]["activate"] = not predictions[0]["activate"]
        report = score(self.cases, predictions, self.thresholds, 1)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["critical_violations"])

    def test_direct_delegation_is_rejected_and_cannot_pass_score(self) -> None:
        predictions = gold_predictions(self.cases, 1)
        predictions[0]["mode"] = "direct"
        predictions[0]["delegate"] = True
        errors = validate_predictions(predictions, {str(case["id"]) for case in self.cases})
        self.assertTrue(any("direct mode cannot delegate" in error for error in errors))
        report = score(self.cases, predictions, self.thresholds, 1)
        self.assertFalse(report["checks"]["topology"])

    def test_missing_repetitions_fail_coverage(self) -> None:
        report = score(self.cases, gold_predictions(self.cases, 1), self.thresholds, 3)
        self.assertFalse(report["checks"]["coverage"])

    def test_blind_export_contains_no_expected_labels(self) -> None:
        exported = [{"id": case["id"], "prompt": case["prompt"]} for case in self.cases]
        self.assertTrue(all(set(item) == {"id", "prompt"} for item in exported))

    def test_score_segments_tags_and_builds_mode_confusion(self) -> None:
        report = score(self.cases, gold_predictions(self.cases, 1), self.thresholds, 1)
        self.assertIn("tag:critical", report["segments"])
        for expected, predictions in report["mode_confusion"].items():
            self.assertEqual({expected}, set(predictions))

    def test_required_untrusted_sources_are_tagged(self) -> None:
        tags = {tag for case in self.cases for tag in case["tags"]}
        self.assertTrue({"code", "documentation", "issue", "log", "tool-output"}.issubset(tags))

    def test_case_and_prediction_contracts_reject_extra_fields(self) -> None:
        cases = [dict(case) for case in self.cases]
        cases[0]["unexpected"] = True
        self.assertTrue(any("case fields" in error for error in validate_cases(cases, self.thresholds)))
        predictions = gold_predictions(self.cases, 1)
        predictions[0]["unexpected"] = True
        self.assertTrue(any("prediction fields" in error for error in validate_predictions(predictions, {str(case["id"]) for case in self.cases})))

    def test_shifted_or_extra_run_numbers_fail_closed(self) -> None:
        predictions = gold_predictions(self.cases, 3)
        for prediction in predictions:
            prediction["run"] = int(prediction["run"]) + 10
        errors = validate_predictions(predictions, {str(case["id"]) for case in self.cases}, 3)
        self.assertTrue(any("runs must be exactly" in error for error in errors))
        self.assertFalse(score(self.cases, predictions, self.thresholds, 3)["checks"]["coverage"])


if __name__ == "__main__":
    unittest.main()
