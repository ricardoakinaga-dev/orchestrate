from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validate_skill import check_markdown, check_placeholders, check_secrets, load_json_strict, parse_frontmatter, parse_simple_yaml, validate


ROOT = Path(__file__).resolve().parents[1]


class ValidateSkillTests(unittest.TestCase):
    def test_repository_skill_is_valid(self) -> None:
        errors, warnings = validate(ROOT)
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_missing_skill_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            errors, _ = validate(Path(temporary))
        self.assertIn("SKILL_MISSING", {item.code for item in errors})

    def test_markdown_link_cannot_escape_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown = root / "doc.md"
            markdown.write_text("[escape](../../outside.txt)\n", encoding="utf-8")
            findings = check_markdown(root, markdown)
        self.assertIn("LINK_ESCAPE", {item.code for item in findings})

    def test_yaml_duplicate_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            yaml_path = Path(temporary) / "openai.yaml"
            yaml_path.write_text('interface:\n  display_name: "A"\n  display_name: "B"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_simple_yaml(yaml_path)

    def test_frontmatter_and_json_duplicate_keys_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "SKILL.md"
            skill.write_text("---\nname: one\nname: two\ndescription: Example\n---\nBody\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate frontmatter key"):
                parse_frontmatter(skill)
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            load_json_strict('{"name":"one","name":"two"}')

    def test_private_key_is_rejected_without_echoing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = root / "accidental.txt"
            marker = "-----BEGIN " + "PRIVATE KEY-----\n"
            secret.write_text(marker + "not-a-real-key\n", encoding="utf-8")
            findings = check_secrets(root)
        self.assertEqual(["PRIVATE_KEY"], [item.code for item in findings])
        self.assertNotIn("not-a-real-key", findings[0].message)

    def test_unresolved_placeholder_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            references = root / "references"
            references.mkdir()
            (references / "bad.md").write_text("Ship {{UNRESOLVED}} now.\n", encoding="utf-8")
            findings = check_placeholders(root)
        self.assertEqual(["PLACEHOLDER"], [item.code for item in findings])

    def test_secret_scanner_rejects_file_symlink_without_reading_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            target = Path(outside) / "external.txt"
            target.write_text("external content must not be scanned", encoding="utf-8")
            (root / "linked.txt").symlink_to(target)
            findings = check_secrets(root)
        self.assertEqual(["UNSAFE_SYMLINK"], [item.code for item in findings])

    def test_secret_scanner_rejects_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            (root / "linked-directory").symlink_to(Path(outside), target_is_directory=True)
            findings = check_secrets(root)
        self.assertEqual(["UNSAFE_SYMLINK"], [item.code for item in findings])


if __name__ == "__main__":
    unittest.main()
