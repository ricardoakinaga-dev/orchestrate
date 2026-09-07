from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.validate_state import overlaps, validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures"


def fixture(name: str) -> object:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        for task in data.get("tasks", []):
            if isinstance(task, dict) and isinstance(task.get("execution"), dict):
                task["execution"]["observed_at"] = observed_at
    return data


class ValidateStateTests(unittest.TestCase):
    def test_valid_state_passes(self) -> None:
        self.assertEqual([], validate(fixture("state-valid.json")))

    def test_overlap_fixture_is_rejected(self) -> None:
        codes = {item.code for item in validate(fixture("state-invalid-overlap.json"))}
        self.assertIn("OWNERSHIP_COLLISION", codes)
        self.assertNotIn("SCHEMA_VERSION", codes)
        self.assertNotIn("EXECUTION_FIELDS", codes)

    def test_transition_fixture_is_rejected_for_multiple_real_reasons(self) -> None:
        codes = {item.code for item in validate(fixture("state-invalid-transition.json"))}
        self.assertTrue({"TRANSITION", "EVIDENCE_MISSING", "DONE_FINDING"}.issubset(codes))
        self.assertNotIn("SCHEMA_VERSION", codes)

    def test_path_and_named_resource_overlap(self) -> None:
        self.assertTrue(overlaps("src/**", "src/api/route.py"))
        self.assertTrue(overlaps("src/*.py", "src/app.py"))
        self.assertTrue(overlaps("db:primary", "db:primary"))
        self.assertFalse(overlaps("db:primary", "db:analytics"))
        self.assertFalse(overlaps("src/api/**", "src/ui/**"))
        self.assertTrue(overlaps("path:src/**", "src/api/**"))
        self.assertTrue(overlaps("src/api/file.py", "src//api/file.py"))
        self.assertTrue(overlaps("src/api/file.py", "src/api/./file.py"))

    def test_stale_contract_is_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["contracts"]["api"] = "v3"
        codes = {item.code for item in validate(state)}
        self.assertIn("CONTRACT_STALE", codes)

    def test_synchronized_contract_change_invalidates_old_evidence(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["contracts"]["api"] = "v3"
        for task in state["tasks"]:
            task["contracts"]["api"] = "v3"
        state["tasks"][0]["criteria"][0]["evidence"][0]["contract_integrity"] = "sha256:51465a4409a03999b8fca03bc7eccab7abac27bc05b14c8c02e8e3334df461fe"
        codes = {item.code for item in validate(state)}
        self.assertTrue({"EVIDENCE_MANIFEST", "EVIDENCE_MISSING"}.issubset(codes))

    def test_ownership_path_cannot_escape_workspace(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["tasks"][1]["owns"] = ["../outside/**"]
        codes = {item.code for item in validate(state)}
        self.assertIn("OWNERSHIP_ESCAPE", codes)

    def test_terminal_shortcuts_and_empty_attempts_are_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["tasks"][0]["history"] = ["DONE"]
        state["tasks"][0]["attempts"] = []
        codes = {item.code for item in validate(state)}
        self.assertTrue({"HISTORY_START", "HISTORY_CHAIN", "ATTEMPT_MISSING"}.issubset(codes))

    def test_unchanged_retry_is_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        first = state["tasks"][1]["attempts"][0]
        state["tasks"][1]["attempts"].append({**first, "number": 2})
        codes = {item.code for item in validate(state)}
        self.assertIn("ATTEMPT_UNCHANGED", codes)

    def test_rephrased_no_evidence_retry_is_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        first = state["tasks"][1]["attempts"][0]
        state["tasks"][1]["attempts"].append({**first, "number": 2, "evidence_delta": "Still no additional evidence was produced."})
        codes = {item.code for item in validate(state)}
        self.assertIn("ATTEMPT_UNCHANGED", codes)

    def test_word_order_cannot_fake_new_retry_evidence(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        first = state["tasks"][1]["attempts"][0]
        state["tasks"][1]["attempts"].append({**first, "number": 2, "evidence_delta": "Evidence remained unchanged."})
        codes = {item.code for item in validate(state)}
        self.assertIn("ATTEMPT_UNCHANGED", codes)

    def test_retry_requires_stable_hypothesis_and_registered_evidence(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        first = state["tasks"][1]["attempts"][0]
        state["tasks"][1]["attempts"].append(
            {
                **first,
                "number": 2,
                "hypothesis_id": "H99",
                "hypothesis": first["hypothesis"] + "!",
                "evidence_refs": ["sha256:" + "a" * 64],
            }
        )
        codes = {item.code for item in validate(state)}
        self.assertTrue({"HYPOTHESIS_ID_REBOUND", "EVIDENCE_REF_UNKNOWN"}.issubset(codes))

    def test_malformed_evidence_refs_return_issues_instead_of_raising(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        first = state["tasks"][1]["attempts"][0]
        state["tasks"][1]["attempts"].append({**first, "number": 2, "evidence_refs": [[{}]]})
        codes = {item.code for item in validate(state)}
        self.assertIn("ATTEMPT_SHAPE", codes)

    def test_unknown_top_level_field_is_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["unexpected"] = True
        codes = {item.code for item in validate(state)}
        self.assertIn("ROOT_FIELDS", codes)

    def test_symlinked_ownership_alias_collides(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "real").mkdir()
            (root / "alias").symlink_to(root / "real", target_is_directory=True)
            state = fixture("state-invalid-overlap.json")
            assert isinstance(state, dict)
            state["tasks"][0]["owns"] = ["real/**"]
            state["tasks"][1]["owns"] = ["alias/**"]
            codes = {item.code for item in validate(state, root)}
            self.assertIn("OWNERSHIP_COLLISION", codes)

    def test_nonexistent_current_pass_artifact_is_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["tasks"][0]["criteria"][0]["evidence"][0]["artifact"] = "does/not/exist"
        codes = {item.code for item in validate(state)}
        self.assertTrue({"EVIDENCE_ARTIFACT_MISSING", "EVIDENCE_MISSING"}.issubset(codes))

    def test_evidence_reached_through_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "evals" / "fixtures").mkdir(parents=True)
            (root / "evals" / "fixtures" / "artifacts").symlink_to(FIXTURES / "artifacts", target_is_directory=True)
            state = fixture("state-valid.json")
            assert isinstance(state, dict)
            codes = {item.code for item in validate(state, root)}
            self.assertIn("EVIDENCE_SYMLINK", codes)

    def test_remote_or_opaque_current_pass_is_not_self_authenticating(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        evidence = state["tasks"][0]["criteria"][0]["evidence"][0]
        evidence["artifact"] = "urn:forged:approval"
        evidence["integrity"] = "trust-me"
        codes = {item.code for item in validate(state)}
        self.assertTrue({"EVIDENCE_UNVERIFIABLE", "EVIDENCE_MISSING"}.issubset(codes))

    def test_normalized_duplicate_ownership_is_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["tasks"][1]["owns"] = ["src/api/file.py", "src//api/./file.py"]
        codes = {item.code for item in validate(state)}
        self.assertIn("OWNERSHIP_DUPLICATE", codes)

    def test_running_task_requires_checkpointed_process_identity(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        del state["tasks"][1]["execution"]
        codes = {item.code for item in validate(state)}
        self.assertTrue({"TASK_FIELDS", "EXECUTION_FIELDS"}.issubset(codes))

    def test_live_validation_rejects_replayed_and_future_checkpoints(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        for task in state["tasks"]:
            if isinstance(task, dict) and isinstance(task.get("execution"), dict):
                task["execution"]["observed_at"] = "2026-09-03T00:00:00Z"
        now = datetime(2026, 9, 3, 0, 10, tzinfo=timezone.utc)
        codes = {item.code for item in validate(state, now=now)}
        self.assertIn("CHECKPOINT_STALE", codes)
        state["tasks"][1]["execution"]["observed_at"] = "2026-09-03T00:11:00Z"
        codes = {item.code for item in validate(state, now=now)}
        self.assertIn("CHECKPOINT_FUTURE", codes)

    def test_pid_reuse_is_detected_by_full_process_identity(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["tasks"][2]["execution"] = dict(state["tasks"][1]["execution"])
        self.assertIn("PROCESS_IDENTITY_COLLISION", {item.code for item in validate(state)})

    def test_contradictory_current_evidence_is_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        evidence = state["tasks"][0]["criteria"][0]["evidence"][0]
        state["tasks"][0]["criteria"][0]["evidence"].append({**evidence, "result": "FAIL"})
        self.assertIn("EVIDENCE_CURRENT_CONFLICT", {item.code for item in validate(state)})

    def test_nested_unknown_fields_are_rejected(self) -> None:
        state = fixture("state-valid.json")
        assert isinstance(state, dict)
        state["tasks"][0]["criteria"][0]["unexpected"] = True
        state["tasks"][0]["open_findings"] = [{"severity": "low", "summary": "x", "unexpected": True}]
        codes = {item.code for item in validate(state)}
        self.assertTrue({"CRITERION_FIELDS", "FINDING_SHAPE"}.issubset(codes))


if __name__ == "__main__":
    unittest.main()
