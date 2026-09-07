#!/usr/bin/env python3
"""Exercise identity-bound interruption recovery against real local processes."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


FAILURE_CLASSES = {"transient", "specification", "implementation", "architecture-integration", "permission-external"}
CHECKPOINTS = {"PENDING", "READY", "RUNNING", "IMPLEMENTED", "REVIEW", "REWORK", "VERIFIED", "DONE", "BLOCKED", "FAILED"}
PROCESS_STATES = {"live", "exited", "missing", "identity-mismatch"}
CHECKPOINT_FIELDS = {"status", "generation", "workspace_sha256", "process_id", "process_start_token", "artifact_path"}
OBSERVATION_FIELDS = {"state", "process_id", "process_start_token", "returncode", "observed_at", "observer"}


def classify_failure(kind: str) -> str:
    if kind not in FAILURE_CLASSES:
        raise ValueError(f"unknown failure class {kind!r}")
    return kind


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None


def process_start_token(process_id: int) -> str:
    """Return Linux start ticks so PID reuse cannot masquerade as the same process."""
    if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id < 1:
        raise ValueError("process_id must be a positive integer")
    stat = Path(f"/proc/{process_id}/stat").read_text(encoding="utf-8")
    suffix = stat[stat.rfind(")") + 2 :].split()
    if len(suffix) < 20:
        raise ValueError("process stat does not contain a start token")
    return suffix[19]


def observe_process(
    process: subprocess.Popen[bytes] | subprocess.Popen[str],
    expected_start_token: str,
    observer: str = "recovery-probe",
) -> dict[str, object]:
    if not isinstance(expected_start_token, str) or not expected_start_token:
        raise ValueError("expected_start_token is required")
    returncode = process.poll()
    try:
        actual_token = process_start_token(process.pid)
    except OSError:
        actual_token = expected_start_token
    state = "identity-mismatch" if actual_token != expected_start_token else "live" if returncode is None else "exited"
    return {
        "state": state,
        "process_id": process.pid,
        "process_start_token": actual_token,
        "returncode": returncode,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "observer": observer,
    }


def reconcile(
    checkpoint: dict[str, object],
    observation: dict[str, object],
    current_workspace_sha256: str,
    root: Path,
    expected_artifact_sha256: str,
    *,
    now: datetime | None = None,
    max_observation_age_seconds: int = 300,
) -> dict[str, object]:
    """Reconcile only from bound process identity and observed artifact bytes."""
    if set(checkpoint) != CHECKPOINT_FIELDS or checkpoint.get("status") not in CHECKPOINTS:
        raise ValueError("checkpoint has invalid fields or status")
    if not isinstance(checkpoint.get("generation"), int) or isinstance(checkpoint.get("generation"), bool) or checkpoint["generation"] < 1:
        raise ValueError("checkpoint generation must be a positive integer")
    if not isinstance(checkpoint.get("process_id"), int) or isinstance(checkpoint.get("process_id"), bool) or checkpoint["process_id"] < 1:
        raise ValueError("checkpoint process_id must be a positive integer")
    if not isinstance(checkpoint.get("process_start_token"), str) or not checkpoint["process_start_token"]:
        raise ValueError("checkpoint process_start_token is required")
    if not isinstance(checkpoint.get("workspace_sha256"), str) or len(str(checkpoint["workspace_sha256"])) != 64:
        raise ValueError("checkpoint workspace_sha256 is invalid")
    if not isinstance(current_workspace_sha256, str) or len(current_workspace_sha256) != 64:
        raise ValueError("current_workspace_sha256 is invalid")
    if not isinstance(expected_artifact_sha256, str) or len(expected_artifact_sha256) != 64:
        raise ValueError("expected_artifact_sha256 is invalid")
    if set(observation) != OBSERVATION_FIELDS or observation.get("state") not in PROCESS_STATES:
        raise ValueError("process observation is invalid")
    if not isinstance(max_observation_age_seconds, int) or isinstance(max_observation_age_seconds, bool) or not 30 <= max_observation_age_seconds <= 3600:
        raise ValueError("max_observation_age_seconds must be an integer from 30 to 3600")
    try:
        observed_at = datetime.fromisoformat(str(observation.get("observed_at", "")).removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError("observation observed_at must be an ISO-8601 UTC timestamp") from exc
    if not str(observation.get("observed_at", "")).endswith("Z"):
        raise ValueError("observation observed_at must use UTC Z notation")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    age = (current_time.astimezone(timezone.utc) - observed_at).total_seconds()
    if age < -5 or age > max_observation_age_seconds:
        return {"status": "BLOCKED", "restart": False, "reason": "process observation is stale or future-dated; acquire a fresh observation"}
    if observation.get("returncode") is not None and (
        not isinstance(observation.get("returncode"), int) or isinstance(observation.get("returncode"), bool)
    ):
        raise ValueError("observation returncode must be an integer or null")
    root = root.resolve()
    artifact_value = checkpoint.get("artifact_path")
    if not isinstance(artifact_value, str) or not artifact_value.strip():
        raise ValueError("checkpoint artifact_path is required")
    artifact = (root / artifact_value).resolve()
    try:
        artifact.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact_path escapes recovery root") from exc
    if checkpoint["workspace_sha256"] != current_workspace_sha256:
        return {"status": "BLOCKED", "restart": False, "reason": "workspace fingerprint changed; revalidation is required"}
    identity_matches = (
        observation.get("process_id") == checkpoint["process_id"]
        and observation.get("process_start_token") == checkpoint["process_start_token"]
        and observation.get("state") != "identity-mismatch"
    )
    if observation.get("state") == "live" and identity_matches and observation.get("returncode") is None:
        return {"status": "RUNNING", "restart": False, "reason": "matching process identity is observably live"}
    artifact_valid = file_sha256(artifact) == expected_artifact_sha256
    if identity_matches and observation.get("state") == "exited" and observation.get("returncode") == 0 and artifact_valid:
        return {"status": "DONE", "restart": False, "reason": "matching process exited successfully and artifact digest is valid"}
    return {"status": "READY", "restart": True, "reason": "no matching live process or valid successful completion; bounded retry may start"}


def run_probe() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="orchestrate-recovery-") as temporary:
        root = Path(temporary)
        artifact = root / "result.txt"
        workspace_digest = "a" * 64
        expected_digest = hashlib.sha256(b"verified").hexdigest()

        live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            live_token = process_start_token(live.pid)
            live_checkpoint = {
                "status": "RUNNING",
                "generation": 1,
                "workspace_sha256": workspace_digest,
                "process_id": live.pid,
                "process_start_token": live_token,
                "artifact_path": "result.txt",
            }
            live_observation = observe_process(live, live_token)
            live_result = reconcile(live_checkpoint, live_observation, workspace_digest, root, expected_digest)
        finally:
            live.terminate()
            live.wait(timeout=5)

        completed = subprocess.Popen(
            [sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('verified', encoding='utf-8')", str(artifact)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        completed_token = process_start_token(completed.pid)
        completed.wait(timeout=5)
        completed_observation = observe_process(completed, completed_token)
        completed_checkpoint = {
            "status": "RUNNING",
            "generation": 2,
            "workspace_sha256": workspace_digest,
            "process_id": completed.pid,
            "process_start_token": completed_token,
            "artifact_path": "result.txt",
        }
        completed_valid = reconcile(completed_checkpoint, completed_observation, workspace_digest, root, expected_digest)
        artifact.write_text("tampered", encoding="utf-8")
        completed_invalid = reconcile(completed_checkpoint, completed_observation, workspace_digest, root, expected_digest)
        identity_mismatch = reconcile(
            completed_checkpoint,
            {**completed_observation, "state": "identity-mismatch", "process_start_token": "reused-pid"},
            workspace_digest,
            root,
            expected_digest,
        )
        stale_workspace = reconcile(completed_checkpoint, completed_observation, "b" * 64, root, expected_digest)
        scenarios = {
            "live-process": live_result,
            "completed-valid": completed_valid,
            "completed-invalid": completed_invalid,
            "identity-mismatch": identity_mismatch,
            "stale-workspace": stale_workspace,
        }
        passed = (
            live_result["status"] == "RUNNING"
            and live_result["restart"] is False
            and completed_valid["status"] == "DONE"
            and completed_valid["restart"] is False
            and completed_invalid["status"] == "READY"
            and completed_invalid["restart"] is True
            and identity_mismatch["status"] == "READY"
            and identity_mismatch["restart"] is True
            and stale_workspace["status"] == "BLOCKED"
            and stale_workspace["restart"] is False
            and len({classify_failure(kind) for kind in FAILURE_CLASSES}) == 5
        )
        return {
            "passed": passed,
            "scenarios": scenarios,
            "process_observation": completed_observation,
            "failure_classes": sorted(FAILURE_CLASSES),
        }


def main() -> int:
    report = run_probe()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
