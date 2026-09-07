from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.validate_routing_receipt import validate, validate_expected_stale


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "evals" / "evidence" / "routing-v2" / "receipt.json"


class ValidateRoutingReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_repository_receipt_is_preserved_but_explicitly_stale(self) -> None:
        strict_errors = validate(self.receipt, ROOT)
        self.assertTrue(any("historical" in error for error in strict_errors))
        self.assertTrue(any(error.startswith("source hash mismatch: ") for error in strict_errors))
        blocking, source_drift = validate_expected_stale(self.receipt, ROOT)
        self.assertEqual([], blocking)
        self.assertTrue(source_drift)
        self.assertFalse(self.receipt["immutable"])
        self.assertFalse(self.receipt["release_authority"])

    def test_expected_stale_mode_does_not_hide_output_tampering(self) -> None:
        receipt = deepcopy(self.receipt)
        receipt["evaluators"][0]["output"]["sha256"] = "0" * 64
        blocking, _source_drift = validate_expected_stale(receipt, ROOT)
        self.assertTrue(any("output hash mismatch" in error for error in blocking))

    def test_immutable_flag_must_be_boolean(self) -> None:
        receipt = deepcopy(self.receipt)
        receipt["immutable"] = "not-yet"
        errors = validate(receipt, ROOT)
        self.assertTrue(any("immutable must be boolean" in error for error in errors))

    def test_immutable_claim_cannot_contradict_limitations(self) -> None:
        receipt = deepcopy(self.receipt)
        receipt["immutable"] = True
        errors = validate(receipt, ROOT)
        self.assertTrue(any("contradicts" in error for error in errors))

    def test_v1_cannot_be_re_attested_by_refreshing_metadata(self) -> None:
        receipt = deepcopy(self.receipt)
        for source in receipt["source_files"]:
            source["sha256"] = __import__("hashlib").sha256((ROOT / source["path"]).read_bytes()).hexdigest()
        receipt["immutable"] = True
        receipt["limitations"] = [item.replace("It is not immutable. ", "") for item in receipt["limitations"]]
        errors = validate(receipt, ROOT)
        self.assertTrue(any("historical" in error for error in errors))

    def test_v2_binds_evaluators_to_a_pre_run_source_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = deepcopy(self.receipt)
            receipt["schema_version"] = 2
            receipt["immutable"] = True
            receipt["limitations"] = [
                "The receipt does not independently prove evaluator blindness or external authenticity.",
                "Routing classification does not prove installed runtime behavior or release readiness.",
            ]
            for source in receipt["source_files"]:
                destination = root / source["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / source["path"], destination)
                source["sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
            dataset = root / receipt["dataset"]["path"]
            dataset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / receipt["dataset"]["path"], dataset)
            snapshot = {
                "schema_version": 1,
                "captured_at": "2026-09-02T00:00:00Z",
                "source_files": receipt["source_files"],
                "dataset": receipt["dataset"],
                "assignment_constraints": receipt["assignment_constraints"],
            }
            snapshot_path = root / "evals" / "evidence" / "routing-v3" / "source-snapshot.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps(snapshot, sort_keys=True) + "\n", encoding="utf-8")
            snapshot_digest = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            receipt["source_snapshot"] = {"path": "evals/evidence/routing-v3/source-snapshot.json", "sha256": snapshot_digest}
            for evaluator in receipt["evaluators"]:
                run = evaluator["run"]
                output = root / "evals" / "evidence" / "routing-v3" / f"run-{run}.jsonl"
                shutil.copy2(ROOT / evaluator["output"]["path"], output)
                evaluator["output"] = {"path": output.relative_to(root).as_posix(), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
                evaluator.pop("session_rollout_sha256")
                session = root / "evals" / "evidence" / "routing-v3" / f"session-{run}.jsonl"
                session.write_text(json.dumps({"type": "thread.started", "thread_id": evaluator["thread_id"]}) + "\n", encoding="utf-8")
                evaluator["session_rollout"] = {"path": session.relative_to(root).as_posix(), "sha256": hashlib.sha256(session.read_bytes()).hexdigest()}
                prompt = root / "evals" / "evidence" / "routing-v3" / f"prompt-{run}.txt"
                prompt.write_text("blind routing prompt\n", encoding="utf-8")
                evaluator["prompt"] = {"path": prompt.relative_to(root).as_posix(), "sha256": hashlib.sha256(prompt.read_bytes()).hexdigest()}
                invocation = root / "evals" / "evidence" / "routing-v3" / f"invocation-{run}.json"
                invocation.write_text(json.dumps({"client": "codex-cli"}) + "\n", encoding="utf-8")
                evaluator["invocation"] = {"path": invocation.relative_to(root).as_posix(), "sha256": hashlib.sha256(invocation.read_bytes()).hexdigest()}
                evaluator["source_snapshot_sha256"] = snapshot_digest
            self.assertEqual([], validate(receipt, root))
            receipt["evaluators"][0]["source_snapshot_sha256"] = "0" * 64
            self.assertTrue(any("not bound" in error for error in validate(receipt, root)))
            receipt["evaluators"][0]["session_rollout"]["sha256"] = "0" * 64
            self.assertTrue(any("session_rollout" in error for error in validate(receipt, root)))

    def test_tampered_output_digest_fails(self) -> None:
        receipt = deepcopy(self.receipt)
        receipt["evaluators"][0]["output"]["sha256"] = "0" * 64
        errors = validate(receipt, ROOT)
        self.assertTrue(any("output hash mismatch" in error for error in errors))

    def test_evaluators_must_be_distinct(self) -> None:
        receipt = deepcopy(self.receipt)
        receipt["evaluators"][1]["thread_id"] = receipt["evaluators"][0]["thread_id"]
        errors = validate(receipt, ROOT)
        self.assertTrue(any("must be distinct" in error for error in errors))

    def test_instruction_source_set_must_be_complete(self) -> None:
        receipt = deepcopy(self.receipt)
        receipt["source_files"] = [item for item in receipt["source_files"] if item["path"] != "references/security.md"]
        errors = validate(receipt, ROOT)
        self.assertTrue(any("routed instruction set" in error for error in errors))

    def test_metadata_must_be_well_formed(self) -> None:
        receipt = deepcopy(self.receipt)
        receipt["evaluators"][0]["cli_version"] = "anything"
        receipt["evaluators"][0]["session_rollout_sha256"] = "not-a-digest"
        receipt["evaluators"][0]["completed_at"] = receipt["evaluators"][0]["started_at"]
        errors = validate(receipt, ROOT)
        self.assertTrue(any("semantic version" in error for error in errors))
        self.assertTrue(any("SHA-256" in error for error in errors))
        self.assertTrue(any("timestamps" in error for error in errors))

    def test_assignment_contract_cannot_contradict_blinding(self) -> None:
        receipt = deepcopy(self.receipt)
        receipt["assignment_constraints"]["allowed_inputs"].append("evals/cases.jsonl with expected labels")
        errors = validate(receipt, ROOT)
        self.assertTrue(any("contradict" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
