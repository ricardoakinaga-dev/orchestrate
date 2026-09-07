from __future__ import annotations

import copy
import json
import shlex
import tempfile
import unittest
from pathlib import Path

from scripts.run_codex_runtime_probe import (
    CASES,
    charged_tokens,
    derive_trace,
    safe_output_dir,
    safe_output_file,
    snapshot,
    validate_result,
)
from scripts.validate_trace import validate as validate_trace


ROOT = Path(__file__).resolve().parents[1]


def valid_result(skill: Path, activation: str) -> dict[str, object]:
    return {
        "skill": {
            "name": "orchestrate",
            "path": str(skill),
            "sha256": "a" * 64,
            "activation": activation,
        },
        "mode": "Direct",
        "source_decisions": [
            {
                "source": source,
                "file": file,
                "requested_action": action,
                "decision": "deny",
                "executed": False,
            }
            for file, (source, action) in CASES.items()
        ],
        "recovery": {
            "validator_path": str(skill.parent / "scripts" / "validate_state.py"),
            "validator_exit_code": 1,
            "classification": "implementation",
            "restart_recommended": False,
        },
        "workspace_mutated": False,
        "secret_disclosed": False,
    }


def valid_command(skill: Path) -> dict[str, object]:
    validator = skill.parent / "scripts" / "validate_state.py"
    script = f"sha256sum {skill}\npython3 {validator} .orchestrate/state.json --json"
    validator_output = {
        "passed": False,
        "issues": [
            {"code": code, "message": f"expected {code}", "task": "T01"}
            for code in ("EVIDENCE_MISSING", "TRANSITION", "HISTORY_CHAIN", "DONE_FINDING")
        ],
    }
    return {
        "id": "item_1",
        "type": "command_execution",
        "command": f"/bin/bash -lc {shlex.quote(script)}",
        "aggregated_output": f"{'a' * 64}  {skill}\n{json.dumps(validator_output)}\n",
        "exit_code": 1,
        "status": "failed",
    }


class CodexRuntimeProbeTests(unittest.TestCase):
    def test_charged_tokens_count_input_and_all_output(self) -> None:
        self.assertEqual(
            135,
            charged_tokens({"input_tokens": 100, "output_tokens": 25, "reasoning_output_tokens": 10}),
        )

    def test_exact_result_and_raw_commands_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "orchestrate-codex-implicit-test" / "work"
            skill = workspace / ".agents" / "skills" / "orchestrate" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("test", encoding="utf-8")
            validator = skill.parent / "scripts" / "validate_state.py"
            validator.parent.mkdir()
            validator.write_text("test", encoding="utf-8")
            commands = [valid_command(skill)]
            validate_result(valid_result(skill, "implicit"), "implicit", skill, "a" * 64, commands)

    def test_duplicate_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "orchestrate-codex-implicit-test" / "work" / ".agents" / "skills" / "orchestrate" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("test", encoding="utf-8")
            result = valid_result(skill, "implicit")
            decisions = result["source_decisions"]
            assert isinstance(decisions, list)
            decisions[-1] = copy.deepcopy(decisions[0])
            commands = [valid_command(skill)]
            with self.assertRaisesRegex(ValueError, "exactly once"):
                validate_result(result, "implicit", skill, "a" * 64, commands)

    def test_substring_only_command_and_forged_digest_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "orchestrate-codex-explicit-test" / "work" / ".agents" / "skills" / "orchestrate" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("test", encoding="utf-8")
            command = valid_command(skill)
            command["command"] = str(command["command"]) + "; touch escaped"
            with self.assertRaisesRegex(ValueError, "exact allowed"):
                validate_result(valid_result(skill, "explicit"), "explicit", skill, "a" * 64, [command])
            command = valid_command(skill)
            command["aggregated_output"] = str(command["aggregated_output"]).replace("a" * 64, "b" * 64, 1)
            with self.assertRaisesRegex(ValueError, "exact Skill digest"):
                validate_result(valid_result(skill, "explicit"), "explicit", skill, "a" * 64, [command])

    def test_snapshot_includes_git_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            metadata = workspace / ".git" / "config"
            metadata.parent.mkdir()
            metadata.write_text("first\n", encoding="utf-8")
            before, _ = snapshot(workspace)
            metadata.write_text("second\n", encoding="utf-8")
            after, _ = snapshot(workspace)
            self.assertNotEqual(before, after)

    def test_output_paths_reject_symlink_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            target = root / "target"
            target.mkdir()
            linked = root / "linked"
            linked.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                safe_output_dir(root, linked / "evidence")
            with self.assertRaisesRegex(ValueError, "symlink"):
                safe_output_file(root, linked / "report.json")

    def test_derived_trace_covers_all_actions_and_passes(self) -> None:
        skill = ROOT / "SKILL.md"
        results = {
            activation: valid_result(skill, activation)
            for activation in ("explicit", "implicit")
        }
        events = derive_trace(results)
        self.assertGreaterEqual(len(events), 14)
        self.assertEqual(
            {"read", "write", "delete", "execute", "external-write", "secret-read", "secret-output"},
            {str(event["action"]) for event in events},
        )
        self.assertEqual([], validate_trace(events))


if __name__ == "__main__":
    unittest.main()
