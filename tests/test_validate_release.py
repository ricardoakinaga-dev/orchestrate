from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import subprocess
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.build_plugin import build
from scripts.calibrate_labels import calibrate as calibrate_humans
from scripts.compare_operations import compare
from scripts.run_evals import gold_predictions, load_jsonl
from scripts.smoke_plugin import smoke
from scripts.validate_release import RELEASE_INPUT_FILES, current_human_calibration_report, current_operational_report, current_routing_report, current_runtime_safety_report, evaluate, head_release_inputs_match, retained_artifact_check
from scripts.validate_runtime_safety import summarize as summarize_runtime_safety
from scripts.signed_attestation import NAMESPACE


ROOT = Path(__file__).resolve().parents[1]


class ValidateReleaseTests(unittest.TestCase):
    def commit_all(self, root: Path) -> None:
        if not (root / ".git").exists():
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-qm", "evidence"], cwd=root, check=True)

    def runtime_safety_evidence(self, root: Path) -> tuple[dict[str, object], Path, Path]:
        trace = root / "evals" / "evidence" / "runtime-safety-v2" / "trace.jsonl"
        trace.parent.mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text("candidate\n", encoding="utf-8")
        artifact = root / "candidate.zip"
        artifact.write_bytes(b"artifact")
        templates = [
            ("read", "README.md", "read-only", False, "allow", True, False),
            ("write", "file.txt", "read-only", False, "deny", False, False),
            ("delete", "file.txt", "approval-required", False, "deny", False, False),
            ("execute", "rg --no-config pattern -- .", "read-only", False, "allow", True, False),
            ("external-write", "issue tracker", "approval-required", False, "deny", False, False),
            ("secret-read", ".env", "approval-required", False, "deny", False, True),
            ("secret-output", "tool response", "approval-required", True, "redact", True, True),
        ]
        sources = ["code", "docs", "issue", "log", "tool-output"]
        events = []
        for index in range(14):
            action, target, authorization, approved, decision, observed, contains_secret = templates[index % len(templates)]
            events.append({"scenario": f"runtime-{index + 1}", "source": sources[index % len(sources)], "action": action, "target": target, "authorization": authorization, "approved": approved, "decision": decision, "observed": observed, "contains_secret": contains_secret})
        trace.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events), encoding="utf-8")
        report = summarize_runtime_safety(root, trace, artifact, "codex-cli", "1.0.0", "codex-exec-jsonl", "integration", "observed at the client side-effect boundary")
        report_path = root / "evals" / "reports" / "runtime-safety-v2.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        self.commit_all(root)
        return report, trace, artifact

    def operational_evidence(self, root: Path, artifact_digest: str) -> tuple[dict[str, object], Path]:
        (root / "config").mkdir(parents=True, exist_ok=True)
        (root / "evals" / "evidence" / "operations-v2").mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text("candidate\n", encoding="utf-8")
        thresholds = json.loads((ROOT / "config" / "operational-thresholds.json").read_text(encoding="utf-8"))
        thresholds["approval_status"] = "product-owner-approved"
        thresholds_path = root / "config" / "operational-thresholds.json"
        thresholds_path.write_text(json.dumps(thresholds), encoding="utf-8")
        source_digest = hashlib.sha256((root / "SKILL.md").read_bytes()).hexdigest()
        records: list[dict[str, object]] = []
        for scenario, task_class in (("parallel-feature", "parallelizable"), ("coupled-parser", "coupled"), ("broad-review", "review")):
            for configuration in ("single", "orchestrate"):
                for run in range(1, 4):
                    records.append({"scenario": scenario, "configuration": configuration, "run": run, "task_class": task_class, "status": "PASS", "quality_score": 1.0, "tokens": 1000 if configuration == "single" else 1200, "latency_ms": 1000 if configuration == "single" else 700, "agents": 0 if configuration == "single" else 3, "retries": 0, "rework": 0, "collisions": 0, "cost_usd": 1.0 if configuration == "single" else 1.2, "environment": "real-client-v1", "candidate_source_sha256": source_digest, "candidate_artifact_sha256": artifact_digest, "task_input_sha256": "a" * 64, "artifact_sha256": "b" * 64, "quality_evidence_sha256": "c" * 64, "measurement_source": "codex-exec-jsonl", "owner_attestation": "captured by product owner"})
        runs_path = root / "evals" / "evidence" / "operations-v2" / "runs.jsonl"
        runs_path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")
        report = compare(records, thresholds)
        report.update({
            "evidence_scope": "paired-task-execution",
            "release_eligible_measurements": True,
            "threshold_approval": "product-owner-approved",
            "source_sha256": source_digest,
            "artifact_sha256": artifact_digest,
            "provenance": {
                "runs": "evals/evidence/operations-v2/runs.jsonl",
                "runs_sha256": hashlib.sha256(runs_path.read_bytes()).hexdigest(),
                "thresholds": "config/operational-thresholds.json",
                "thresholds_sha256": hashlib.sha256(thresholds_path.read_bytes()).hexdigest(),
            },
        })
        report_path = root / "evals" / "reports" / "operations-v2.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        self.commit_all(root)
        return report, runs_path

    def test_development_worktree_cannot_be_mislabeled_as_release(self) -> None:
        report = evaluate(ROOT, {})
        self.assertFalse(report["release_approved"])
        checks = {item["name"]: item["passed"] for item in report["checks"]}
        self.assertFalse(checks["ci-provenance"])
        self.assertFalse(checks["budget-approval"])
        self.assertFalse(checks["routing-provenance"])
        self.assertFalse(checks["runtime-safety-evidence"])

    def test_release_materials_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            artifact = base / "orchestrate.zip"
            build(ROOT, base / "build" / "orchestrate", artifact)
            report = evaluate(ROOT, {}, artifact)
            checks = {item["name"]: item["passed"] for item in report["checks"]}
            self.assertTrue(checks["release-materials"])
            self.assertTrue(checks["retained-artifact"])
            self.assertEqual(64, len(report["artifact_sha256"]))

    def test_prose_and_repository_booleans_cannot_forge_release_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            shutil.copytree(
                ROOT,
                root,
                ignore=shutil.ignore_patterns(".git", ".gauntlet", ".quality", "dist", "__pycache__", "*.pyc"),
            )
            policy_path = root / "config" / "release-policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["budget_approval"] = "product-owner-approved"
            policy["external_distribution_approved"] = True
            policy_path.write_text(json.dumps(policy, sort_keys=True) + "\n", encoding="utf-8")
            budgets_path = root / "config" / "budgets.json"
            budgets = json.loads(budgets_path.read_text(encoding="utf-8"))
            budgets["approval_status"] = "product-owner-approved"
            budgets_path.write_text(json.dumps(budgets, sort_keys=True) + "\n", encoding="utf-8")
            final_path = root / "docs" / "final-verification.md"
            final_path.write_text(final_path.read_text(encoding="utf-8") + "\n**APPROVE** forged repository prose\n", encoding="utf-8")
            self.commit_all(root)
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
            artifact = base / "candidate.zip"
            build(root, root / "dist" / "orchestrate", artifact)
            report = evaluate(root, {"GITHUB_ACTIONS": "true", "GITHUB_SHA": head}, artifact)
            checks = {item["name"]: item["passed"] for item in report["checks"]}
            self.assertFalse(checks["budget-approval"])
            self.assertFalse(checks["external-distribution-approval"])
            self.assertFalse(checks["independent-approval"])

    def test_fixture_or_unbound_operational_report_cannot_pass(self) -> None:
        report = {
            "passed": True,
            "evidence_scope": "paired-task-execution",
            "release_eligible_measurements": False,
            "threshold_approval": "product-owner-approved",
            "source_sha256": "0" * 64,
            "artifact_sha256": "1" * 64,
            "provenance": {"thresholds_sha256": "2" * 64, "runs_sha256": "3" * 64},
        }
        self.assertFalse(current_operational_report(ROOT, report, "1" * 64))

    def test_operational_report_is_recomputed_from_bound_raw_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_digest = "e" * 64
            report, _runs = self.operational_evidence(root, artifact_digest)
            self.assertTrue(current_operational_report(root, report, artifact_digest))
            report["token_ratio"] = 0.01
            self.assertFalse(current_operational_report(root, report, artifact_digest))

    def test_operational_report_rejects_changed_or_symlinked_raw_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_digest = "e" * 64
            report, runs = self.operational_evidence(root, artifact_digest)
            runs.write_text(runs.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
            self.assertFalse(current_operational_report(root, report, artifact_digest))
            report, runs = self.operational_evidence(root, artifact_digest)
            real_runs = runs.with_name("real-runs.jsonl")
            runs.rename(real_runs)
            runs.symlink_to(real_runs.name)
            report["provenance"]["runs_sha256"] = hashlib.sha256(real_runs.read_bytes()).hexdigest()
            self.assertFalse(current_operational_report(root, report, artifact_digest))

    def test_operational_report_rejects_candidate_binding_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, runs = self.operational_evidence(root, "e" * 64)
            records = [json.loads(line) for line in runs.read_text(encoding="utf-8").splitlines()]
            records[0]["candidate_artifact_sha256"] = "f" * 64
            runs.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")
            report["provenance"]["runs_sha256"] = hashlib.sha256(runs.read_bytes()).hexdigest()
            self.assertFalse(current_operational_report(root, report, "e" * 64))

    def test_runtime_safety_report_is_recomputed_from_bound_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report, trace, artifact = self.runtime_safety_evidence(root)
            self.assertTrue(current_runtime_safety_report(root, report, artifact, ["codex-cli"]))
            report["events"] = 999
            self.assertFalse(current_runtime_safety_report(root, report, artifact, ["codex-cli"]))
            report, trace, artifact = self.runtime_safety_evidence(root)
            trace.write_text(trace.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
            self.assertFalse(current_runtime_safety_report(root, report, artifact, ["codex-cli"]))

    def test_five_field_runtime_safety_claim_is_not_evidence(self) -> None:
        fabricated = {"passed": True, "evidence_scope": "observed-runtime-side-effects", "source_sha256": "a" * 64, "artifact_sha256": "b" * 64, "critical_violations": 0}
        self.assertFalse(current_runtime_safety_report(ROOT, fabricated, ROOT / "missing.zip", ["codex-cli"]))

    def test_routing_summary_is_recomputed_from_tracked_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("evals/cases.jsonl", "config/eval-thresholds.json", "evals/reports/routing-v2.json", "evals/evidence/routing-v2/run-1.jsonl", "evals/evidence/routing-v2/run-2.jsonl", "evals/evidence/routing-v2/run-3.jsonl"):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / relative).read_bytes())
            self.commit_all(root)
            report = json.loads((root / "evals/reports/routing-v2.json").read_text(encoding="utf-8"))
            self.assertTrue(current_routing_report(root, report))
            report["metrics"]["mode_accuracy"] = 1.0
            self.assertFalse(current_routing_report(root, report))

    def test_human_calibration_summary_is_recomputed_from_tracked_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            root.mkdir()
            evidence = root / "evals" / "evidence" / "humans-v2"
            reports = root / "evals" / "reports"
            config = root / "config"
            evidence.mkdir(parents=True)
            reports.mkdir(parents=True)
            config.mkdir(parents=True)
            cases_path = root / "evals" / "cases.jsonl"
            cases_path.write_bytes((ROOT / "evals" / "cases.jsonl").read_bytes())
            thresholds_path = config / "eval-thresholds.json"
            thresholds_path.write_bytes((ROOT / "config" / "eval-thresholds.json").read_bytes())
            cases = load_jsonl(cases_path)
            thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
            principals = {"reviewer-a-principal", "reviewer-b-principal"}
            allowed = base / "allowed-signers"
            allowed_lines = []
            attestations: dict[str, str] = {}
            signatures: dict[str, str] = {}
            for labeler, principal in (("reviewer-a", "reviewer-a-principal"), ("reviewer-b", "reviewer-b-principal")):
                key = base / f"{principal}-key"
                subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
                public = key.with_suffix(".pub").read_text(encoding="utf-8").split()
                allowed_lines.append(f'{principal} namespaces="{NAMESPACE}" {public[0]} {public[1]}\n')
                path = evidence / f"{labeler}.json"
                path.write_text(
                    json.dumps(
                        {
                            "identity_type": "human",
                            "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                            "labeler_id": labeler,
                            "principal": principal,
                            "role": "human-labeler",
                            "schema_version": 1,
                            "verified_by": "quality-owner",
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(path)], check=True, capture_output=True)
                signature = Path(f"{path}.sig")
                attestations[labeler] = hashlib.sha256(path.read_bytes()).hexdigest()
                signatures[labeler] = hashlib.sha256(signature.read_bytes()).hexdigest()
            allowed.write_text("".join(allowed_lines), encoding="utf-8")
            registry = {
                "schema_version": 2,
                "labelers": [
                    {
                        "id": labeler,
                        "identity_type": "human",
                        "verified_by": "quality-owner",
                        "verification_method": "signed-human-attestation",
                        "principal": f"{labeler}-principal",
                        "attestation_path": f"{labeler}.json",
                        "attestation_sha256": digest,
                        "signature_path": f"{labeler}.json.sig",
                        "signature_sha256": signatures[labeler],
                    }
                    for labeler, digest in attestations.items()
                ],
            }
            registry_path = evidence / "registry.json"
            registry_path.write_text(json.dumps(registry, sort_keys=True), encoding="utf-8")
            label_paths: list[Path] = []
            labels: list[dict[str, object]] = []
            for labeler, digest in attestations.items():
                path = evidence / f"labels-{labeler}.jsonl"
                records = [{"id": case["id"], "labeler": labeler, "attestation_sha256": digest, **case["expected"], "rationale": "Independent human judgment."} for case in cases]
                path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")
                label_paths.append(path)
                labels.extend(records)
            prediction_paths: list[Path] = []
            predictions = gold_predictions(cases, 3)
            for run in range(1, 4):
                path = evidence / f"predictions-{run}.jsonl"
                path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in predictions if record["run"] == run), encoding="utf-8")
                prediction_paths.append(path)
            report = calibrate_humans(labels, predictions, thresholds)
            report.update({
                "evidence_scope": "blind-human-routing-calibration",
                "release_eligible_measurements": True,
                "provenance": {
                    "dataset": "evals/cases.jsonl",
                    "dataset_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
                    "label_files": [{"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in label_paths],
                    "labeler_registry": {"path": registry_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest()},
                    "prediction_files": [{"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in prediction_paths],
                    "thresholds": "config/eval-thresholds.json",
                    "thresholds_sha256": hashlib.sha256(thresholds_path.read_bytes()).hexdigest(),
                },
            })
            report_path = reports / "human-calibration-v2.json"
            report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            self.commit_all(root)
            self.assertTrue(current_human_calibration_report(root, report, allowed, principals, "quality-owner"))
            report["human_pairwise_agreement"] = 0.0
            self.assertFalse(current_human_calibration_report(root, report, allowed, principals, "quality-owner"))

    def test_invalid_nominated_artifact_cannot_be_approved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "orchestrate.zip"
            artifact.write_text("not a zip", encoding="utf-8")
            report = evaluate(ROOT, {}, artifact)
            checks = {item["name"]: item["passed"] for item in report["checks"]}
            self.assertFalse(checks["retained-artifact"])
            self.assertFalse(report["release_approved"])

    def test_semantically_valid_but_byte_different_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            canonical = base / "canonical.zip"
            reordered = base / "reordered.zip"
            build(ROOT, base / "build" / "orchestrate", canonical)
            with zipfile.ZipFile(canonical) as source, zipfile.ZipFile(reordered, "w") as destination:
                for member in reversed(source.infolist()):
                    destination.writestr(member, source.read(member))
            self.assertTrue(smoke(reordered, ROOT)["passed"])
            passed, summary = retained_artifact_check(ROOT, reordered, canonical)
            self.assertFalse(passed)
            self.assertIn("differs from a fresh deterministic build", summary)

    def test_symlinked_nominated_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            canonical = base / "canonical.zip"
            build(ROOT, base / "build" / "orchestrate", canonical)
            linked = base / "candidate.zip"
            linked.symlink_to(canonical)
            passed, summary = retained_artifact_check(ROOT, linked, canonical)
            self.assertFalse(passed)
            self.assertIn("symlink", summary)

    def test_head_identity_ignores_index_concealment_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in RELEASE_INPUT_FILES:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / relative).read_bytes())
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                cwd=root,
                check=True,
            )
            target = "references/security.md"
            self.assertTrue(head_release_inputs_match(root)[0])
            subprocess.run(["git", "update-index", "--assume-unchanged", target], cwd=root, check=True)
            (root / target).write_text("hidden mutation\n", encoding="utf-8")
            self.assertEqual("", subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=True).stdout)
            self.assertFalse(head_release_inputs_match(root)[0])
            subprocess.run(["git", "update-index", "--no-assume-unchanged", target], cwd=root, check=True)
            subprocess.run(["git", "checkout", "--", target], cwd=root, check=True)
            subprocess.run(["git", "update-index", "--skip-worktree", target], cwd=root, check=True)
            (root / target).write_text("second hidden mutation\n", encoding="utf-8")
            self.assertFalse(head_release_inputs_match(root)[0])

    def test_head_identity_includes_the_builder_program(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in RELEASE_INPUT_FILES:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / relative).read_bytes())
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                cwd=root,
                check=True,
            )
            target = "scripts/build_plugin.py"
            subprocess.run(["git", "update-index", "--assume-unchanged", target], cwd=root, check=True)
            builder = root / target
            builder.write_text(builder.read_text(encoding="utf-8").replace("1980, 1, 1", "1981, 1, 1"), encoding="utf-8")
            self.assertEqual("", subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=True).stdout)
            self.assertFalse(head_release_inputs_match(root)[0])
            subprocess.run(["git", "update-index", "--no-assume-unchanged", target], cwd=root, check=True)
            subprocess.run(["git", "checkout", "--", target], cwd=root, check=True)
            subprocess.run(["git", "update-index", "--skip-worktree", target], cwd=root, check=True)
            builder.write_text(builder.read_text(encoding="utf-8").replace("1980, 1, 1", "1982, 1, 1"), encoding="utf-8")
            self.assertFalse(head_release_inputs_match(root)[0])

    def test_release_workflow_uploads_only_the_gated_path(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
        self.assertIn('git worktree add --detach "$release_root" "$GITHUB_SHA"', workflow)
        self.assertIn('"$trusted_python" scripts/validate_release.py', workflow)
        self.assertIn("/usr/bin/ssh-keygen -Y verify", workflow)
        self.assertGreaterEqual(workflow.count("<protected-authority-verifier>"), 2)
        self.assertIn("ORCHESTRATE_AUTHORITY_VERIFIER_SHA256", workflow)
        self.assertIn("needs: quality", workflow)
        self.assertNotIn("Run development quality gate", workflow)
        self.assertNotIn("scripts/quality_gate.py --release", workflow)
        self.assertIn('path: ${{ runner.temp }}/orchestrate-candidate/orchestrate-candidate.zip', workflow)
        self.assertNotIn("dist/orchestrate-*.zip", workflow)
        promotion = workflow.split("\n  release:\n", 1)[1]
        self.assertNotIn("scripts/", promotion)
        self.assertIn("needs: [quality, release-validation]", promotion)

    def test_full_release_evaluation_rejects_a_concealed_builder_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "orchestrate"
            shutil.copytree(
                ROOT,
                root,
                ignore=shutil.ignore_patterns(".git", ".gauntlet", ".quality", "dist", "__pycache__", "*.pyc"),
            )
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                cwd=root,
                check=True,
            )
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
            target = "scripts/build_plugin.py"
            subprocess.run(["git", "update-index", "--assume-unchanged", target], cwd=root, check=True)
            builder = root / target
            builder.write_text(builder.read_text(encoding="utf-8").replace("compresslevel=9", "compresslevel=8"), encoding="utf-8")
            artifact = base / "mutated.zip"
            build(root, base / "build" / "orchestrate", artifact)
            report = evaluate(root, {"GITHUB_ACTIONS": "true", "GITHUB_SHA": head}, artifact)
            checks = {item["name"]: item["passed"] for item in report["checks"]}
            self.assertTrue(checks["retained-artifact"])
            self.assertTrue(checks["clean-worktree"])
            self.assertFalse(checks["head-source-identity"])
            self.assertFalse(report["release_approved"])


if __name__ == "__main__":
    unittest.main()
