from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build_plugin import build, render_manifest


ROOT = Path(__file__).resolve().parents[1]


class BuildPluginTests(unittest.TestCase):
    def test_manifest_matches_version(self) -> None:
        manifest = render_manifest(ROOT)
        self.assertEqual("orchestrate", manifest["name"])
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), manifest["version"])

    def test_build_contains_exact_skill_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "orchestrate"
            archive = Path(temporary) / "plugin.zip"
            result = build(ROOT, output, archive)
            packaged = output / "skills" / "orchestrate" / "SKILL.md"
            self.assertEqual((ROOT / "SKILL.md").read_bytes(), packaged.read_bytes())
            self.assertTrue((output / "skills" / "orchestrate" / "scripts" / "validate_state.py").is_file())
            self.assertFalse((output / "skills" / "orchestrate" / "scripts" / "build_plugin.py").exists())
            self.assertTrue((output / "LICENSE.md").is_file())
            self.assertTrue((output / "RELEASE_NOTES.md").is_file())
            manifest = json.loads((output / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual("./skills/", manifest["skills"])
            self.assertEqual("UNLICENSED", manifest["license"])
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), result["sha256"])

    def test_archives_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = base / "first.zip"
            second = base / "second.zip"
            build(ROOT, base / "one" / "orchestrate", first)
            build(ROOT, base / "two" / "orchestrate", second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_ignored_or_hidden_source_content_is_not_packaged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            replica = base / "source"
            shutil.copytree(
                ROOT,
                replica,
                ignore=shutil.ignore_patterns(".git", ".gauntlet", ".quality", "dist", "__pycache__", "*.pyc"),
            )
            hidden = replica / "references" / ".orchestrate" / "injected.txt"
            hidden.parent.mkdir()
            hidden.write_text("must not ship", encoding="utf-8")
            output = base / "build" / "orchestrate"
            build(replica, output, base / "plugin.zip")
            self.assertFalse((output / "skills" / "orchestrate" / "references" / ".orchestrate").exists())


if __name__ == "__main__":
    unittest.main()
