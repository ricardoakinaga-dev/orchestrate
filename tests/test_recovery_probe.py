from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.recovery_probe import FAILURE_CLASSES, classify_failure, observe_process, process_start_token, reconcile, run_probe


class RecoveryProbeTests(unittest.TestCase):
    def test_all_failure_classes_are_explicit(self) -> None:
        self.assertEqual(5, len({classify_failure(kind) for kind in FAILURE_CLASSES}))
        with self.assertRaises(ValueError):
            classify_failure("mystery")

    def test_real_live_process_is_not_restarted(self) -> None:
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            token = process_start_token(process.pid)
            self.assertEqual("live", observe_process(process, token)["state"])
        finally:
            process.terminate()
            process.wait(timeout=5)

    def test_completed_artifact_wins_only_with_identity_and_digest(self) -> None:
        report = run_probe()
        self.assertTrue(report["passed"])
        self.assertFalse(report["scenarios"]["completed-valid"]["restart"])
        self.assertTrue(report["scenarios"]["completed-invalid"]["restart"])

    def test_pid_identity_mismatch_and_workspace_drift_fail_closed(self) -> None:
        report = run_probe()
        self.assertEqual("READY", report["scenarios"]["identity-mismatch"]["status"])
        self.assertEqual("BLOCKED", report["scenarios"]["stale-workspace"]["status"])

    def test_missing_identity_cannot_be_interpreted_as_live(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = hashlib.sha256(b"verified").hexdigest()
            checkpoint = {
                "status": "RUNNING",
                "generation": 1,
                "workspace_sha256": "a" * 64,
                "process_id": 123,
                "process_start_token": "start-1",
                "artifact_path": "result.txt",
            }
            observation = {
                "state": "missing",
                "process_id": 123,
                "process_start_token": "start-1",
                "returncode": None,
                "observed_at": "2026-09-03T00:00:00Z",
                "observer": "test",
            }
            result = reconcile(checkpoint, observation, "a" * 64, root, expected, now=datetime(2026, 9, 3, 0, 1, tzinfo=timezone.utc))
            self.assertEqual("READY", result["status"])
            self.assertTrue(result["restart"])

    def test_replayed_live_observation_is_blocked(self) -> None:
        checkpoint = {"status": "RUNNING", "generation": 1, "workspace_sha256": "a" * 64, "process_id": 123, "process_start_token": "start-1", "artifact_path": "result.txt"}
        observation = {"state": "live", "process_id": 123, "process_start_token": "start-1", "returncode": None, "observed_at": "2000-01-01T00:00:00Z", "observer": "replayed"}
        result = reconcile(checkpoint, observation, "a" * 64, Path.cwd(), "b" * 64)
        self.assertEqual("BLOCKED", result["status"])
        self.assertFalse(result["restart"])
        self.assertIn("fresh observation", result["reason"])

    def test_malformed_reconciliation_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            reconcile({}, {}, "a" * 64, Path.cwd(), "b" * 64)


if __name__ == "__main__":
    unittest.main()
