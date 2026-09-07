from __future__ import annotations

import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.run_codex_routing_probe import (
    assignment_constraints,
    build_prompt,
    dataset_descriptor,
    parse_session,
    source_files,
    write_bundle,
)
from scripts.run_evals import gold_predictions, load_jsonl
from scripts.verify_codex_routing_probe import verify
from scripts.validate_routing_receipt import REQUIRED_SOURCE_FILES


ROOT = Path(__file__).resolve().parents[1]


def raw_session(run: int, thread_id: str, predictions: list[dict[str, object]], *, with_command: bool = False) -> str:
    events: list[dict[str, object]] = [
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
    ]
    if with_command:
        events.append({
            "type": "item.completed",
            "item": {"id": "bad", "type": "command_execution", "command": "cat evals/cases.jsonl"},
        })
    events.extend([
        {
            "type": "item.completed",
            "item": {
                "id": "answer",
                "type": "agent_message",
                "text": json.dumps({"predictions": predictions}, ensure_ascii=False),
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "cache_write_input_tokens": 0,
                "output_tokens": 50,
                "reasoning_output_tokens": 25,
            },
        },
    ])
    return "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events)


class CodexRoutingProbeTests(unittest.TestCase):
    def test_prompt_contains_only_frozen_sources_and_blind_records(self) -> None:
        prompt = build_prompt(ROOT, 1)
        cases = load_jsonl(ROOT / "evals" / "cases.jsonl")
        self.assertEqual(len(cases), prompt.count("<blind-request id="))
        self.assertEqual(len(REQUIRED_SOURCE_FILES), prompt.count("<instruction-source path="))
        self.assertNotIn(cases[0]["rationale"], prompt)
        self.assertTrue(assignment_constraints()["gold_labels_denied"])

    def test_parser_rejects_tool_use(self) -> None:
        cases = load_jsonl(ROOT / "evals" / "cases.jsonl")
        predictions = gold_predictions(cases, 1)
        case_ids = [str(case["id"]) for case in cases]
        with self.assertRaisesRegex(ValueError, "tool or command"):
            parse_session(raw_session(1, "11111111-1111-1111-1111-111111111111", predictions, with_command=True), 1, case_ids)

    def test_bundle_recomputes_from_three_raw_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in sorted(REQUIRED_SOURCE_FILES):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            for relative in (
                "evals/cases.jsonl",
                "config/eval-thresholds.json",
                "schemas/codex-routing-probe-output.schema.json",
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            cases = load_jsonl(root / "evals" / "cases.jsonl")
            snapshot = {
                "schema_version": 1,
                "captured_at": "2026-09-04T00:00:00Z",
                "source_files": source_files(root),
                "dataset": dataset_descriptor(root),
                "assignment_constraints": assignment_constraints(),
            }
            runs: list[dict[str, object]] = []
            for run in (1, 2, 3):
                predictions = gold_predictions(cases, 1)
                for prediction in predictions:
                    prediction["run"] = run
                thread_id = f"{run:08x}-1111-1111-1111-{run:012x}"
                usage = {
                    "input_tokens": 100,
                    "cached_input_tokens": 0,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 50,
                    "reasoning_output_tokens": 25,
                }
                invocation = {
                    "schema_version": 1,
                    "client": "codex-cli",
                    "client_version": "0.153.0",
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "high",
                    "ephemeral": True,
                    "ignore_user_config": True,
                    "ignore_rules": True,
                    "sandbox": "read-only",
                    "shell_environment_inherit": "none",
                    "output_schema_sha256": hashlib.sha256(
                        (root / "schemas" / "codex-routing-probe-output.schema.json").read_bytes()
                    ).hexdigest(),
                    "exit_code": 0,
                    "stderr": "Reading additional input from stdin...\n",
                    "usage": usage,
                    "charged_tokens": 175,
                }
                runs.append({
                    "run": run,
                    "thread_id": thread_id,
                    "started_at": f"2026-09-04T00:0{run}:00Z",
                    "completed_at": f"2026-09-04T00:0{run}:01Z",
                    "tokens_used": 175,
                    "usage": usage,
                    "prompt": build_prompt(root, run),
                    "raw": raw_session(run, thread_id, predictions),
                    "stderr": "Reading additional input from stdin...\n",
                    "predictions": predictions,
                    "invocation": invocation,
                })
            result = write_bundle(
                root,
                root / "evals" / "evidence" / "routing-v3",
                root / "evals" / "reports" / "routing-v3.json",
                "0.153.0",
                "gpt-5.6-sol",
                "high",
                snapshot,
                runs,
            )
            self.assertTrue(result["passed"])
            verified = verify(root)
            self.assertTrue(verified["passed"])
            self.assertEqual(132, verified["predictions"])


if __name__ == "__main__":
    unittest.main()
