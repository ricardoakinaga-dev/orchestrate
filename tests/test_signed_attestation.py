from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.signed_attestation import NAMESPACE, external_trust_anchor, load_signed_statement, principals_have_distinct_keys
from scripts.validate_release import current_final_attestation, current_product_attestation, sha256
from scripts.verify_release_authority import verify as verify_external_authority


class SignedAttestationTests(unittest.TestCase):
    def make_identity(self, base: Path, principal: str) -> tuple[Path, Path]:
        key = base / "signing-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        fields = key.with_suffix(".pub").read_text(encoding="utf-8").split()
        allowed = base / "allowed-signers"
        allowed.write_text(f'{principal} namespaces="{NAMESPACE}" {fields[0]} {fields[1]}\n', encoding="utf-8")
        return key, allowed

    def statement(self, base: Path, key: Path, principal: str) -> tuple[Path, Path, datetime]:
        now = datetime.now(timezone.utc)
        statement = base / "statement.json"
        statement.write_text(
            json.dumps(
                {
                    "issued_at": now.isoformat().replace("+00:00", "Z"),
                    "principal": principal,
                    "role": "test",
                    "schema_version": 1,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(statement)],
            check=True,
            capture_output=True,
        )
        return statement, Path(f"{statement}.sig"), now

    def sign_payload(self, path: Path, key: Path, payload: dict[str, object]) -> Path:
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", NAMESPACE, str(path)],
            check=True,
            capture_output=True,
        )
        return Path(f"{path}.sig")

    def test_valid_signature_is_accepted_and_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            key, allowed = self.make_identity(base, "release-owner")
            statement, signature, now = self.statement(base, key, "release-owner")
            self.assertIsNotNone(load_signed_statement(statement, signature, allowed, "release-owner", now=now))
            statement.write_text(statement.read_text(encoding="utf-8").replace('"test"', '"forged"'), encoding="utf-8")
            self.assertIsNone(load_signed_statement(statement, signature, allowed, "release-owner", now=now))

    def test_wrong_principal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            key, allowed = self.make_identity(base, "release-owner")
            statement, signature, now = self.statement(base, key, "release-owner")
            self.assertIsNone(load_signed_statement(statement, signature, allowed, "different-owner", now=now))

    def test_distinct_roles_cannot_share_a_signing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            key, allowed = self.make_identity(base, "owner")
            public = key.with_suffix(".pub").read_text(encoding="utf-8").split()
            with allowed.open("a", encoding="utf-8") as handle:
                handle.write(f'verifier namespaces="{NAMESPACE}" {public[0]} {public[1]}\n')
            self.assertFalse(principals_have_distinct_keys(allowed, ["owner", "verifier"]))

    def test_trust_anchor_must_be_external_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            root.mkdir()
            _key, allowed = self.make_identity(base, "release-owner")
            digest = hashlib.sha256(allowed.read_bytes()).hexdigest()
            environment = {
                "ORCHESTRATE_ALLOWED_SIGNERS": str(allowed),
                "ORCHESTRATE_ALLOWED_SIGNERS_SHA256": digest,
            }
            self.assertEqual(allowed.resolve(), external_trust_anchor(root, environment))
            environment["ORCHESTRATE_ALLOWED_SIGNERS_SHA256"] = "0" * 64
            self.assertIsNone(external_trust_anchor(root, environment))
            internal = root / "allowed-signers"
            internal.write_bytes(allowed.read_bytes())
            environment.update(
                ORCHESTRATE_ALLOWED_SIGNERS=str(internal),
                ORCHESTRATE_ALLOWED_SIGNERS_SHA256=hashlib.sha256(internal.read_bytes()).hexdigest(),
            )
            self.assertIsNone(external_trust_anchor(root, environment))

    def test_symlinked_signature_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            key, allowed = self.make_identity(base, "release-owner")
            statement, signature, now = self.statement(base, key, "release-owner")
            real_signature = base / "real.sig"
            signature.rename(real_signature)
            signature.symlink_to(real_signature.name)
            self.assertIsNone(load_signed_statement(statement, signature, allowed, "release-owner", now=now))

    def test_path_poisoning_cannot_replace_the_signature_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            key, allowed = self.make_identity(base, "release-owner")
            statement, _signature, now = self.statement(base, key, "release-owner")
            bogus_signature = base / "bogus.sig"
            bogus_signature.write_text("not an OpenSSH signature\n", encoding="utf-8")
            fake_bin = base / "bin"
            fake_bin.mkdir()
            fake = fake_bin / "ssh-keygen"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            with mock.patch.dict("os.environ", {"PATH": str(fake_bin)}):
                self.assertIsNone(load_signed_statement(statement, bogus_signature, allowed, "release-owner", now=now))

    def test_release_roles_are_bound_to_exact_candidate_and_distinct_principals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            (root / "config").mkdir(parents=True)
            (root / "SKILL.md").write_text("candidate\n", encoding="utf-8")
            for name in ("release-quality-bar.json", "budgets.json", "operational-thresholds.json"):
                (root / "config" / name).write_text("{}\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "candidate"],
                cwd=root,
                check=True,
            )
            keys: dict[str, Path] = {}
            allowed_lines: list[str] = []
            principals = ("owner", "verifier", "human-a", "human-b")
            for principal in principals:
                key = base / f"{principal}-key"
                subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
                public = key.with_suffix(".pub").read_text(encoding="utf-8").split()
                allowed_lines.append(f'{principal} namespaces="{NAMESPACE}" {public[0]} {public[1]}\n')
                keys[principal] = key
            allowed = base / "allowed-signers"
            allowed.write_text("".join(allowed_lines), encoding="utf-8")
            now = datetime.now(timezone.utc)
            issued_at = now.isoformat().replace("+00:00", "Z")
            final_issued_at = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
            artifact_path = base / "candidate.zip"
            artifact_path.write_bytes(b"candidate artifact")
            artifact_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            product_path = base / "product.json"
            product_signature = self.sign_payload(
                product_path,
                keys["owner"],
                {
                    "artifact_sha256": artifact_digest,
                    "budgets_sha256": sha256(root / "config" / "budgets.json"),
                    "external_distribution_approved": True,
                    "head": head,
                    "human_labeler_principals": ["human-a", "human-b"],
                    "issued_at": issued_at,
                    "operational_thresholds_sha256": sha256(root / "config" / "operational-thresholds.json"),
                    "principal": "owner",
                    "quality_bar_sha256": sha256(root / "config" / "release-quality-bar.json"),
                    "role": "product-owner",
                    "schema_version": 1,
                    "skill_sha256": sha256(root / "SKILL.md"),
                },
            )
            environment = {
                "ORCHESTRATE_ALLOWED_SIGNERS": str(allowed),
                "ORCHESTRATE_ALLOWED_SIGNERS_SHA256": hashlib.sha256(allowed.read_bytes()).hexdigest(),
                "ORCHESTRATE_PRODUCT_OWNER_ATTESTATION": str(product_path),
                "ORCHESTRATE_PRODUCT_OWNER_SIGNATURE": str(product_signature),
                "ORCHESTRATE_PRODUCT_OWNER_PRINCIPAL": "owner",
                "ORCHESTRATE_FINAL_VERIFIER_PRINCIPAL": "verifier",
            }
            product = current_product_attestation(root, environment, allowed, head, artifact_digest, now=now)
            self.assertIsNotNone(product)
            final_path = base / "final.json"
            final_signature = self.sign_payload(
                final_path,
                keys["verifier"],
                {
                    "artifact_sha256": artifact_digest,
                    "head": head,
                    "issued_at": final_issued_at,
                    "principal": "verifier",
                    "product_attestation_sha256": sha256(product_path),
                    "product_signature_sha256": sha256(product_signature),
                    "quality_bar_sha256": sha256(root / "config" / "release-quality-bar.json"),
                    "role": "independent-verifier",
                    "schema_version": 1,
                    "skill_sha256": sha256(root / "SKILL.md"),
                    "verdict": "APPROVE",
                },
            )
            environment.update(
                ORCHESTRATE_FINAL_VERIFIER_ATTESTATION=str(final_path),
                ORCHESTRATE_FINAL_VERIFIER_SIGNATURE=str(final_signature),
            )
            final = current_final_attestation(root, environment, allowed, head, artifact_digest, product_path, product_signature, product, now=now)
            self.assertIsNotNone(final)
            with mock.patch.dict("os.environ", {"PATH": str(base / "untrusted-bin")}):
                external = verify_external_authority(
                    Namespace(
                        root=root,
                        artifact=None,
                        allowed_signers=allowed,
                        allowed_signers_sha256=hashlib.sha256(allowed.read_bytes()).hexdigest(),
                        product_attestation=product_path,
                        product_signature=product_signature,
                        product_principal="owner",
                        final_attestation=final_path,
                        final_signature=final_signature,
                        final_principal="verifier",
                    )
                )
            self.assertTrue(external["passed"])
            self.assertEqual("preflight", external["scope"])
            exact_arguments = Namespace(
                root=root,
                artifact=artifact_path,
                allowed_signers=allowed,
                allowed_signers_sha256=hashlib.sha256(allowed.read_bytes()).hexdigest(),
                product_attestation=product_path,
                product_signature=product_signature,
                product_principal="owner",
                final_attestation=final_path,
                final_signature=final_signature,
                final_principal="verifier",
            )
            self.assertEqual("exact-artifact", verify_external_authority(exact_arguments)["scope"])
            self.assertIsNone(current_final_attestation(root, environment, allowed, "c" * 40, artifact_digest, product_path, product_signature, product, now=now))
            final_payload = json.loads(final_path.read_text(encoding="utf-8"))
            final_payload["issued_at"] = issued_at
            final_signature.unlink()
            self.sign_payload(final_path, keys["verifier"], final_payload)
            self.assertIsNone(current_final_attestation(root, environment, allowed, head, artifact_digest, product_path, product_signature, product, now=now))
            with self.assertRaisesRegex(ValueError, "strictly postdate"):
                verify_external_authority(exact_arguments)
            earlier = now.replace(microsecond=0).timestamp() - 86400
            final_payload["issued_at"] = datetime.fromtimestamp(earlier, timezone.utc).isoformat().replace("+00:00", "Z")
            final_signature.unlink()
            self.sign_payload(final_path, keys["verifier"], final_payload)
            self.assertIsNone(current_final_attestation(root, environment, allowed, head, artifact_digest, product_path, product_signature, product, now=now))


if __name__ == "__main__":
    unittest.main()
