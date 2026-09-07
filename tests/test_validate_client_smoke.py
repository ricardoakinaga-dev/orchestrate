from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.validate_client_smoke import validate, validate_artifacts


ROOT = Path(__file__).resolve().parents[1]


class ValidateClientSmokeTests(unittest.TestCase):
    def test_truthful_unsupported_probe_passes_validation(self) -> None:
        data = json.loads((ROOT / "evals" / "fixtures" / "client-smoke-codex-cli-0.153.0.json").read_text(encoding="utf-8"))
        self.assertEqual([], validate(data))

    def test_supported_cannot_hide_a_not_run_check(self) -> None:
        data = json.loads((ROOT / "evals" / "fixtures" / "client-smoke-codex-cli-0.153.0.json").read_text(encoding="utf-8"))
        data["support_status"] = "SUPPORTED"
        errors = validate(data)
        self.assertTrue(any("SUPPORTED requires" in error for error in errors))

    def test_supported_requires_bound_artifact_for_every_check(self) -> None:
        data = json.loads((ROOT / "evals" / "fixtures" / "client-smoke-codex-cli-0.153.0.json").read_text(encoding="utf-8"))
        data["client_version"] = "1.0.0"
        data["support_status"] = "SUPPORTED"
        for check in data["checks"]:
            check["status"] = "PASS"
        self.assertTrue(any("bound evidence artifact" in error for error in validate(data)))

    def test_supported_artifacts_are_recomputed_and_hash_bound(self) -> None:
        data = json.loads((ROOT / "evals" / "fixtures" / "client-smoke-codex-cli-0.153.0.json").read_text(encoding="utf-8"))
        data["support_status"] = "SUPPORTED"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, check in enumerate(data["checks"]):
                path = root / "evidence" / f"check-{index}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = f"check-{index}\n".encode()
                path.write_bytes(payload)
                check["status"] = "PASS"
                check["artifact"] = {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            self.assertEqual([], validate(data))
            self.assertEqual([], validate_artifacts(data, root))
            data["checks"][0]["artifact"]["sha256"] = "0" * 64
            self.assertIn("installation artifact SHA-256 mismatch", validate_artifacts(data, root))


if __name__ == "__main__":
    unittest.main()
