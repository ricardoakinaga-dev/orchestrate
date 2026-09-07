#!/usr/bin/env python3
"""Run the complete dependency-free quality gate for Orchestrate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(name: str, command: list[str], root: Path, expected_exit_codes: tuple[int, ...] = (0,)) -> dict[str, object]:
    started = time.monotonic()
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    elapsed = round(time.monotonic() - started, 3)
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    return {"name": name, "passed": completed.returncode in expected_exit_codes, "exit_code": completed.returncode, "expected_exit_codes": list(expected_exit_codes), "seconds": elapsed}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--release", action="store_true", help="also require every release-only gate")
    args = parser.parse_args()
    python = sys.executable
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    checks = [
        ("skill", [python, "scripts/validate_skill.py", str(root)]),
        ("docs", [python, "scripts/validate_docs.py", str(root)]),
        ("budgets", [python, "scripts/validate_budgets.py"]),
        ("eval-dataset", [python, "scripts/run_evals.py", "validate"]),
        ("eval-development-dataset", [python, "scripts/run_evals.py", "validate", "--dataset", "evals/dev-cases.jsonl", "--minimum-cases", "12"]),
        ("eval-leakage", [python, "scripts/check_eval_leakage.py", "evals/dev-cases.jsonl", "evals/cases.jsonl"]),
        ("eval-harness", [python, "scripts/run_evals.py", "selftest"]),
        (
            "blind-routing-evidence",
            [
                python,
                "scripts/run_evals.py",
                "score",
                "--predictions",
                "evals/evidence/routing-v2/run-1.jsonl",
                "evals/evidence/routing-v2/run-2.jsonl",
                "evals/evidence/routing-v2/run-3.jsonl",
                "--min-runs",
                "3",
            ],
        ),
        (
            "blind-routing-receipt-staleness",
            [python, "scripts/validate_routing_receipt.py", "--expect-stale-sources"],
        ),
        ("recovery-probe", [python, "scripts/recovery_probe.py"]),
        ("trace-policy-safe", [python, "scripts/validate_trace.py", "evals/fixtures/trace-valid.jsonl"]),
        (
            "client-smoke-evidence",
            [python, "scripts/validate_client_smoke.py", "evals/reports/client-smoke-codex-cli.json", "--verify-artifacts", "--root", str(root)],
        ),
        (
            "codex-runtime-probe-evidence",
            [python, "scripts/verify_codex_runtime_probe.py", "--artifact", f"dist/orchestrate-{version}.zip"],
        ),
        ("tests", [python, "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ]
    results = [run(name, command, root) for name, command in checks]
    results.append(run("trace-policy-known-bad", [python, "scripts/validate_trace.py", "evals/fixtures/trace-invalid.jsonl"], root, (1,)))

    with tempfile.TemporaryDirectory(prefix="orchestrate-quality-") as temporary:
        temp = Path(temporary)
        archives: list[Path] = []
        for number in (1, 2):
            output = temp / f"build-{number}" / "orchestrate"
            archive = temp / f"orchestrate-{number}.zip"
            results.append(run(f"build-{number}", [python, "scripts/build_plugin.py", "--output", str(output), "--archive", str(archive)], root))
            archives.append(archive)
        results.append(run("plugin-smoke-and-rollback", [python, "scripts/smoke_plugin.py", str(archives[0]), "--source-root", str(root)], root))
        deterministic = all(path.is_file() for path in archives) and digest(archives[0]) == digest(archives[1])
        results.append({"name": "deterministic-archive", "passed": deterministic, "exit_code": 0 if deterministic else 1, "seconds": 0.0})

    report = {
        "passed": all(bool(item["passed"]) for item in results),
        "scope": "release" if args.release else "local-development",
        "release_approved": False,
        "version": version,
        "checks": results,
    }
    if args.release:
        retained_archive = root / "dist" / f"orchestrate-{version}.zip"
        results.append(
            run(
                "retained-release-build",
                [python, "scripts/build_plugin.py", "--output", str(root / "dist" / "orchestrate"), "--archive", str(retained_archive)],
                root,
            )
        )
        release = run("release-only-gates", [python, "scripts/validate_release.py", "--artifact", str(retained_archive)], root)
        results.append(release)
        report["passed"] = all(bool(item["passed"]) for item in results)
        report["release_approved"] = bool(report["passed"])
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
