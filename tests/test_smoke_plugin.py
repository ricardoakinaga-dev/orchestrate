from __future__ import annotations

import tempfile
import unittest
import zipfile
import stat
from pathlib import Path

from scripts.build_plugin import build
from scripts.smoke_plugin import safe_members, smoke


ROOT = Path(__file__).resolve().parents[1]


class SmokePluginTests(unittest.TestCase):
    def test_install_and_rollback_in_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive = base / "orchestrate.zip"
            build(ROOT, base / "build" / "orchestrate", archive)
            result = smoke(archive, ROOT)
            self.assertTrue(result["passed"])
            self.assertEqual("1.0.0", result["rollback_version"])

    def test_path_traversal_archive_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", "unsafe")
            with zipfile.ZipFile(archive) as bundle:
                with self.assertRaises(ValueError):
                    safe_members(bundle)

    def test_symlink_archive_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "unsafe.zip"
            member = zipfile.ZipInfo("orchestrate/skills/orchestrate/SKILL.md")
            member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(member, "../../outside")
            with zipfile.ZipFile(archive) as bundle:
                with self.assertRaisesRegex(ValueError, "non-regular"):
                    safe_members(bundle)

    def test_unexpected_archive_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            archive = base / "orchestrate.zip"
            build(ROOT, base / "build" / "orchestrate", archive)
            with zipfile.ZipFile(archive, "a") as bundle:
                bundle.writestr("orchestrate/unexpected.txt", "injected")
            with self.assertRaisesRegex(ValueError, "archive membership mismatch"):
                smoke(archive, ROOT)

    def test_modified_runtime_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            original = base / "original.zip"
            modified = base / "modified.zip"
            build(ROOT, base / "build" / "orchestrate", original)
            target = "orchestrate/skills/orchestrate/references/security.md"
            with zipfile.ZipFile(original) as source, zipfile.ZipFile(modified, "w") as destination:
                for member in source.infolist():
                    content = b"substituted\n" if member.filename == target else source.read(member)
                    destination.writestr(member, content)
            with self.assertRaisesRegex(ValueError, "differs from canonical"):
                smoke(modified, ROOT)


if __name__ == "__main__":
    unittest.main()
