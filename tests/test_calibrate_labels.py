from __future__ import annotations

import json
import subprocess
import unittest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.calibrate_labels import calibrate, sha256, validate_labeler_registry, validate_labels
from scripts.signed_attestation import NAMESPACE


ATTESTATION = "d" * 64

def label(case_id: str, labeler: str, mode: str = "direct") -> dict[str, object]:
    return {"id": case_id, "labeler": labeler, "attestation_sha256": ATTESTATION, "activate": True, "mode": mode, "delegate": mode != "direct", "authorization": "read-only", "rationale": "Independent judgment."}


def prediction(record: dict[str, object], run: int = 1) -> dict[str, object]:
    return {
        "id": record["id"],
        "run": run,
        "activate": record["activate"],
        "mode": record["mode"],
        "delegate": record["delegate"],
        "authorization": record["authorization"],
        "critical_violation": False,
        "rationale": "Blind evaluator judgment.",
    }


class CalibrateLabelsTests(unittest.TestCase):
    thresholds = {"human_pairwise_agreement_min": 0.9, "grader_human_agreement_min": 0.95}

    def signed_registry(self, root: Path) -> tuple[dict[str, object], Path, set[str]]:
        principals = {"human-a", "human-b"}
        allowed = root / "allowed-signers"
        entries = []
        allowed_lines = []
        for labeler, principal in (("A", "human-a"), ("B", "human-b")):
            key = root / f"{principal}-key"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
            public = key.with_suffix(".pub").read_text(encoding="utf-8").split()
            allowed_lines.append(f'{principal} namespaces="{NAMESPACE}" {public[0]} {public[1]}\n')
            attestation = root / f"{labeler}.json"
            attestation.write_text(
                json.dumps(
                    {
                        "identity_type": "human",
                        "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "labeler_id": labeler,
                        "principal": principal,
                        "role": "human-labeler",
                        "schema_version": 1,
                        "verified_by": "release-owner",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(attestation)],
                check=True,
                capture_output=True,
            )
            signature = Path(f"{attestation}.sig")
            entries.append(
                {
                    "id": labeler,
                    "identity_type": "human",
                    "verified_by": "release-owner",
                    "verification_method": "signed-human-attestation",
                    "principal": principal,
                    "attestation_path": attestation.name,
                    "attestation_sha256": sha256(attestation),
                    "signature_path": signature.name,
                    "signature_sha256": sha256(signature),
                }
            )
        allowed.write_text("".join(allowed_lines), encoding="utf-8")
        return {"schema_version": 2, "labelers": entries}, allowed, principals

    def test_unanimous_humans_and_grader_pass(self) -> None:
        labels = [label("ACT-001", "A"), label("ACT-001", "B")]
        predictions = [prediction(labels[0])]
        self.assertEqual([], validate_labels(labels, {"ACT-001"}, verified_labelers={"A": ATTESTATION, "B": ATTESTATION}))
        self.assertTrue(calibrate(labels, predictions, self.thresholds)["passed"])

    def test_human_tie_cannot_authorize_grader(self) -> None:
        labels = [label("ACT-001", "A", "direct"), label("ACT-001", "B", "scout-assisted")]
        predictions = [prediction(labels[0])]
        report = calibrate(labels, predictions, self.thresholds)
        self.assertFalse(report["checks"]["complete_consensus"])

    def test_every_case_needs_two_independent_labelers(self) -> None:
        labels = [label("ACT-001", "A"), label("ACT-001", "B"), label("ACT-002", "A")]
        errors = validate_labels(labels, {"ACT-001", "ACT-002"}, verified_labelers={"A": ATTESTATION, "B": ATTESTATION})
        self.assertIn("ACT-002: has 1 independent labelers; requires 2", errors)

    def test_agent_named_labelers_and_missing_attestations_are_rejected(self) -> None:
        labels = [label("ACT-001", "gpt-agent-a"), label("ACT-001", "gpt-agent-b")]
        errors = validate_labels(labels, {"ACT-001"})
        self.assertTrue(any("agent/model" in error for error in errors))
        self.assertTrue(any("verified human attestation" in error for error in errors))

    def test_registry_binds_human_identity_to_local_attestation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry, allowed, principals = self.signed_registry(root)
            verified, errors = validate_labeler_registry(registry, root, allowed, principals, "release-owner")
            self.assertEqual([], errors)
            self.assertEqual({"A", "B"}, set(verified))

    def test_unsigned_or_unauthorized_registry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry, allowed, principals = self.signed_registry(root)
            self.assertTrue(validate_labeler_registry(registry, root)[1])
            self.assertTrue(validate_labeler_registry(registry, root, allowed, {"human-a"}, "release-owner")[1])
            signature = root / str(registry["labelers"][0]["signature_path"])
            signature.write_text("forged\n", encoding="utf-8")
            registry["labelers"][0]["signature_sha256"] = sha256(signature)
            self.assertTrue(validate_labeler_registry(registry, root, allowed, principals, "release-owner")[1])

    def test_duplicate_prediction_runs_do_not_change_macro_weighting(self) -> None:
        labels = [label("ACT-001", "A"), label("ACT-001", "B"), label("ACT-002", "A"), label("ACT-002", "B")]
        first = prediction(labels[0], 1)
        second = prediction(labels[2], 1)
        report = calibrate(labels, [first, second], self.thresholds)
        self.assertTrue(report["checks"]["uniform_prediction_runs"])
        self.assertEqual(1.0, report["grader_human_agreement"])


if __name__ == "__main__":
    unittest.main()
