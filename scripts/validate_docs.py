#!/usr/bin/env python3
"""Validate documentation traceability and the executable backlog DAG."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    from scripts.build_plugin import RUNTIME_FILES
    from scripts.json_strict import loads as strict_json_loads
    from scripts.validate_routing_receipt import validate as validate_routing_receipt
except ModuleNotFoundError:
    from build_plugin import RUNTIME_FILES
    from json_strict import loads as strict_json_loads
    from validate_routing_receipt import validate as validate_routing_receipt


REQUIRED = {
    "index.md",
    "assessment-report.md",
    "executive-plan.md",
    "roadmap.md",
    "backlog.md",
    "implementation-status.md",
    "final-verification.md",
    "compatibility.md",
    "architecture-verification.md",
    "security-verification.md",
    "release-verification.md",
    "adr/0001-layout-and-distribution.md",
}
STALE_INDEX_PHRASES = {
    "transformação ainda não implementada",
    "Evals comportamentais e CI: ausentes",
}
CURRENT_STATE_KEYS = {
    "routing_receipt",
    "retained_artifact",
    "budget_approval",
    "operational_approval",
    "runtime_safety",
    "operational_benchmark",
    "human_calibration",
    "external_trust_anchor",
    "signed_product_authority",
    "signed_independent_verdict",
    "git_provenance",
    "release",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_is_current(root: Path) -> bool:
    packaged = root / "dist" / "orchestrate" / "skills" / "orchestrate"
    return packaged.is_dir() and all(
        (packaged / relative).is_file() and not (packaged / relative).is_symlink() and (packaged / relative).read_bytes() == (root / relative).read_bytes()
        for relative in RUNTIME_FILES
    )


def observed_state(root: Path) -> dict[str, str]:
    receipt_path = root / "evals" / "evidence" / "routing-v2" / "receipt.json"
    try:
        receipt = strict_json_loads(receipt_path.read_text(encoding="utf-8"))
        routing_current = not validate_routing_receipt(receipt, root)
    except (OSError, ValueError, json.JSONDecodeError):
        routing_current = False
    try:
        budget = strict_json_loads((root / "config" / "budgets.json").read_text(encoding="utf-8"))
        operational = strict_json_loads((root / "config" / "operational-thresholds.json").read_text(encoding="utf-8"))
        if not isinstance(budget, dict) or not isinstance(operational, dict):
            raise ValueError("budget documents must be JSON objects")
    except (OSError, ValueError, json.JSONDecodeError):
        budget, operational = {}, {}
    git_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    clean = git_status.returncode == 0 and not git_status.stdout.strip()
    states = {
        "routing_receipt": "CURRENT" if routing_current else "STALE",
        "retained_artifact": "CURRENT" if artifact_is_current(root) else "STALE",
        "budget_approval": "APPROVED" if budget.get("approval_status") == "product-owner-approved" else "PENDING",
        "operational_approval": "APPROVED" if operational.get("approval_status") == "product-owner-approved" else "PENDING",
        "runtime_safety": "PRESENT" if (root / "evals" / "reports" / "runtime-safety-v2.json").is_file() else "MISSING",
        "operational_benchmark": "PRESENT" if (root / "evals" / "reports" / "operations-v2.json").is_file() else "MISSING",
        "human_calibration": "PRESENT" if (root / "evals" / "reports" / "human-calibration-v2.json").is_file() else "MISSING",
        "external_trust_anchor": "MISSING",
        "signed_product_authority": "MISSING",
        "signed_independent_verdict": "MISSING",
        "git_provenance": "CURRENT" if clean else "UNCOMMITTED",
    }
    states["release"] = "APPROVED" if all(
        states[key] in {"CURRENT", "APPROVED", "PRESENT"} for key in CURRENT_STATE_KEYS - {"release"}
    ) else "BLOCKED"
    return states


def ids(pattern: str, text: str) -> set[str]:
    return set(re.findall(pattern, text, flags=re.MULTILINE))


def parse_backlog(text: str) -> tuple[dict[str, list[str]], set[str]]:
    graph: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not re.match(r"^\| ORC-\d{3} ", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        item = cells[0]
        if item in graph:
            raise ValueError(f"duplicate backlog item {item}")
        graph[item] = re.findall(r"ORC-\d{3}", cells[5])
    details = ids(r"^### (ORC-\d{3}) ", text)
    return graph, details


def validate(root: Path) -> list[str]:
    docs = root / "docs"
    errors: list[str] = []
    present = {path.relative_to(docs).as_posix() for path in docs.rglob("*.md")}
    missing_files = REQUIRED - present
    if missing_files:
        errors.append(f"missing documents: {', '.join(sorted(missing_files))}")
        return errors

    report = (docs / "assessment-report.md").read_text(encoding="utf-8")
    plan = (docs / "executive-plan.md").read_text(encoding="utf-8")
    roadmap = (docs / "roadmap.md").read_text(encoding="utf-8")
    backlog = (docs / "backlog.md").read_text(encoding="utf-8")
    index = (docs / "index.md").read_text(encoding="utf-8")
    implementation = (docs / "implementation-status.md").read_text(encoding="utf-8")
    for phrase in STALE_INDEX_PHRASES:
        if phrase in index:
            errors.append(f"index contains stale current-state claim: {phrase}")
    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else ""
    if version and version not in index:
        errors.append("index does not identify the current VERSION")
    hash_match = re.search(r"\*\*Hash de `SKILL\.md`:\*\* `([0-9a-f]{64})`", implementation)
    actual_skill_hash = sha256(root / "SKILL.md") if (root / "SKILL.md").is_file() else ""
    if not hash_match or hash_match.group(1) != actual_skill_hash:
        errors.append("implementation-status SKILL.md hash does not match the current source")
    documented_state = dict(re.findall(r"^\| `([a-z_]+)` \| `([A-Z]+)` \|$", implementation, flags=re.MULTILINE))
    if set(documented_state) != CURRENT_STATE_KEYS:
        errors.append(f"implementation-status state keys must be exactly {sorted(CURRENT_STATE_KEYS)}")
    else:
        actual_state = observed_state(root)
        mismatches = {key: {"documented": documented_state[key], "actual": actual_state[key]} for key in sorted(CURRENT_STATE_KEYS) if documented_state[key] != actual_state[key]}
        if mismatches:
            errors.append(f"implementation-status current-state mismatch: {mismatches}")
    release_notes = root / "RELEASE_NOTES.md"
    if not release_notes.is_file() or version not in release_notes.read_text(encoding="utf-8"):
        errors.append("release notes are missing or do not identify VERSION")
    license_path = root / "LICENSE.md"
    if not license_path.is_file():
        errors.append("explicit license status is missing")

    definitions = {
        "F": ids(r"^### (F-\d{3}) ", report),
        "OBJ": ids(r"^\| (OBJ-\d{2}) ", plan),
        "QG": ids(r"^\| (QG-\d{2}) ", plan),
        "M": ids(r"^### (M\d) ", roadmap),
    }
    mapped_findings = ids(r"^\| `(F-\d{3})`", index)
    if definitions["F"] != mapped_findings:
        errors.append(f"finding traceability mismatch: defined={sorted(definitions['F'])}, mapped={sorted(mapped_findings)}")

    try:
        graph, detail_ids = parse_backlog(backlog)
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    if set(graph) != detail_ids:
        errors.append("backlog overview/detail IDs differ")
    for item, dependencies in graph.items():
        unknown = set(dependencies) - set(graph)
        if unknown:
            errors.append(f"{item} has unknown dependencies: {sorted(unknown)}")
        if item in dependencies:
            errors.append(f"{item} depends on itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item: str) -> None:
        if item in visiting:
            raise ValueError(f"dependency cycle at {item}")
        if item in visited:
            return
        visiting.add(item)
        for dependency in graph.get(item, []):
            visit(dependency)
        visiting.remove(item)
        visited.add(item)

    try:
        for item in graph:
            visit(item)
    except ValueError as exc:
        errors.append(str(exc))

    combined = "\n".join(path.read_text(encoding="utf-8") for path in docs.rglob("*.md"))
    patterns = {"F": r"F-\d{3}", "OBJ": r"OBJ-\d{2}", "QG": r"QG-\d{2}", "M": r"M\d"}
    for family, pattern in patterns.items():
        referenced = set(re.findall(pattern, combined))
        unknown = referenced - definitions[family]
        if unknown:
            errors.append(f"undefined {family} references: {sorted(unknown)}")
    referenced_orc = set(re.findall(r"ORC-\d{3}", combined))
    unknown_orc = referenced_orc - set(graph)
    if unknown_orc:
        errors.append(f"undefined ORC references: {sorted(unknown_orc)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    for error in errors:
        print(f"ERROR DOCS: {error}")
    print(f"validate_docs: {'PASS' if not errors else 'FAIL'} ({len(errors)} errors)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
