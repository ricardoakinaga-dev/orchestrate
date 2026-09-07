from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.run_codex_runtime_probe import validate_result
from scripts.verify_codex_runtime_probe import verify_probe_bundle


ROOT = Path(__file__).resolve().parents[1]


class VerifyCodexRuntimeProbeTests(unittest.TestCase):
    def test_current_raw_probe_bundle_recomputes(self) -> None:
        result = verify_probe_bundle(ROOT, ROOT / "dist" / "orchestrate-2.0.0-rc.3.zip")
        self.assertTrue(result["passed"])
        self.assertEqual(28, result["trace_events"])

    def test_external_regular_artifact_is_allowed_but_symlink_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "candidate.zip"
            shutil.copy2(ROOT / "dist" / "orchestrate-2.0.0-rc.3.zip", copied)
            self.assertTrue(verify_probe_bundle(ROOT, copied)["passed"])
            linked = Path(temporary) / "linked.zip"
            linked.symlink_to(copied)
            with self.assertRaisesRegex(ValueError, "symlink"):
                verify_probe_bundle(ROOT, linked)

    def test_stored_result_cannot_substitute_skill_digest(self) -> None:
        receipt = json.loads(
            (ROOT / "evals" / "evidence" / "client-smoke-codex-cli-0.153.0" / "explicit-invocation.json").read_text(encoding="utf-8")
        )
        result = copy.deepcopy(receipt["result"])
        result["skill"]["sha256"] = "0" * 64
        skill_path = Path(result["skill"]["path"])
        raw_events = [
            json.loads(line)
            for line in (ROOT / receipt["raw_jsonl"]).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        commands = [
            event["item"]
            for event in raw_events
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "command_execution"
        ]
        with self.assertRaisesRegex(ValueError, "exact skill"):
            validate_result(result, "explicit", skill_path, "a" * 64, commands)


if __name__ == "__main__":
    unittest.main()
