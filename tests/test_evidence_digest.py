from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.evidence_digest import create_digest


class EvidenceDigestTests(unittest.TestCase):
    def test_large_log_is_bounded_and_secret_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.log"
            sanitized = Path(temporary) / "run.sanitized.log"
            fake_token = "sk" + "-" + "A" * 24
            path.write_text("start\n" + fake_token + "\n" + "x" * 5000, encoding="utf-8")
            digest = create_digest(path, sanitized, "synthetic check", 0, 300)
            self.assertTrue(digest["truncated"])
            self.assertLessEqual(len(digest["excerpt"]), 300)
            self.assertNotIn(fake_token, digest["excerpt"])
            self.assertIn("[REDACTED]", digest["excerpt"])
            self.assertNotIn(fake_token, sanitized.read_text(encoding="utf-8"))
            self.assertEqual(str(sanitized), digest["artifact"])
            self.assertTrue(digest["artifact_sanitized"])

    def test_raw_log_cannot_be_reused_as_sanitized_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.log"
            path.write_text("content", encoding="utf-8")
            with self.assertRaises(ValueError):
                create_digest(path, path, "synthetic check", 0)


if __name__ == "__main__":
    unittest.main()
