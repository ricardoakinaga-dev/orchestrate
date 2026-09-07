from __future__ import annotations

import unittest
import shutil
import tempfile
from pathlib import Path

from scripts.validate_docs import STALE_INDEX_PHRASES, parse_backlog, validate


ROOT = Path(__file__).resolve().parents[1]


class ValidateDocsTests(unittest.TestCase):
    def test_documentation_is_traceable(self) -> None:
        self.assertEqual([], validate(ROOT))

    def test_backlog_overview_matches_details(self) -> None:
        text = (ROOT / "docs" / "backlog.md").read_text(encoding="utf-8")
        graph, details = parse_backlog(text)
        self.assertEqual(set(graph), details)
        self.assertEqual(32, len(graph))

    def test_index_does_not_present_the_historical_baseline_as_current(self) -> None:
        index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
        self.assertTrue(all(phrase not in index for phrase in STALE_INDEX_PHRASES))

    def test_false_current_skill_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / "repo"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", ".gauntlet", "__pycache__"))
            status = copy / "docs" / "implementation-status.md"
            text = status.read_text(encoding="utf-8")
            status.write_text(text.replace("**Hash de `SKILL.md`:** `", "**Hash de `SKILL.md`:** `" + "0" * 64 + "<!--"), encoding="utf-8")
            self.assertTrue(any("SKILL.md hash" in error for error in validate(copy)))


if __name__ == "__main__":
    unittest.main()
