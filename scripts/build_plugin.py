#!/usr/bin/env python3
"""Build a deterministic local plugin from the canonical root skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

try:
    from scripts.validate_skill import load_json_strict
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from validate_skill import load_json_strict


RUNTIME_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "assets/icon-large.svg",
    "assets/icon-small.svg",
    "references/agent-brief.md",
    "references/delegation.md",
    "references/orchestration-workflow.md",
    "references/recovery.md",
    "references/security.md",
    "references/task-graph.md",
    "references/verification.md",
    "scripts/evidence_digest.py",
    "scripts/json_strict.py",
    "scripts/validate_state.py",
    "schemas/orchestration-state.schema.json",
    "config/budgets.json",
)
PLUGIN_SOURCE_FILES = (
    "assets/icon-large.svg",
    "assets/icon-small.svg",
    "LICENSE.md",
    "RELEASE_NOTES.md",
)
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_manifest(root: Path) -> dict[str, object]:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER_RE.fullmatch(version):
        raise ValueError(f"invalid semantic version {version!r}")
    template = (root / "packaging" / "plugin.template.json").read_text(encoding="utf-8")
    manifest = load_json_strict(template.replace("${VERSION}", version))
    if not isinstance(manifest, dict):
        raise ValueError("plugin manifest must be a JSON object")
    required = {"name", "version", "description", "author", "license", "skills", "interface"}
    missing = required - manifest.keys()
    if missing:
        raise ValueError(f"manifest is missing fields: {sorted(missing)}")
    if manifest["name"] != "orchestrate" or manifest["version"] != version:
        raise ValueError("manifest identity/version mismatch")
    if manifest["license"] != "UNLICENSED":
        raise ValueError("manifest license must match the repository's no-grant status")
    interface = manifest["interface"]
    if not isinstance(interface, dict):
        raise ValueError("manifest interface must be an object")
    for field in ("displayName", "shortDescription", "longDescription", "developerName", "category", "capabilities", "defaultPrompt"):
        if field not in interface:
            raise ValueError(f"manifest interface is missing {field}")
    prompts = interface["defaultPrompt"]
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3 or any(not isinstance(item, str) or len(item) > 128 for item in prompts):
        raise ValueError("defaultPrompt must contain 1-3 strings of at most 128 characters")
    return manifest


def rendered_manifest_bytes(root: Path) -> bytes:
    return (json.dumps(render_manifest(root), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def plugin_source_files() -> dict[str, str]:
    """Map every packaged, source-backed file to its canonical repository file."""
    files = {f"skills/orchestrate/{entry}": entry for entry in RUNTIME_FILES}
    files.update({entry: entry for entry in PLUGIN_SOURCE_FILES})
    return files


def expected_plugin_files() -> set[str]:
    return {".codex-plugin/plugin.json", *plugin_source_files()}


def copy_file(source: Path, destination: Path, entry: str) -> None:
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"missing or unsafe source file {entry}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_source(root: Path, skill_output: Path) -> None:
    skill_output.mkdir(parents=True, exist_ok=False)
    for entry in RUNTIME_FILES:
        copy_file(root / entry, skill_output / entry, entry)


def deterministic_zip(plugin_root: Path, archive: Path) -> str:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(item for item in plugin_root.rglob("*") if item.is_file()):
            relative = Path(plugin_root.name) / path.relative_to(plugin_root)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return sha256(archive)


def build(root: Path, output: Path, archive: Path | None = None) -> dict[str, object]:
    root = root.resolve()
    output = output.resolve()
    if output.exists():
        allowed_root = (root / "dist").resolve()
        if output.name != "orchestrate" or output.parent != allowed_root:
            raise ValueError(f"refusing to replace unsafe output path {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    manifest = render_manifest(root)
    manifest_dir = output / ".codex-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_bytes(rendered_manifest_bytes(root))
    copy_source(root, output / "skills" / "orchestrate")
    for entry in PLUGIN_SOURCE_FILES:
        copy_file(root / entry, output / entry, entry)
    result: dict[str, object] = {
        "plugin": str(output),
        "version": manifest["version"],
        "files": len([path for path in output.rglob("*") if path.is_file()]),
    }
    if archive is not None:
        result["archive"] = str(archive.resolve())
        result["sha256"] = deterministic_zip(output, archive.resolve())
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--output", type=Path, default=root / "dist" / "orchestrate")
    parser.add_argument("--archive", type=Path, default=root / "dist" / f"orchestrate-{version}.zip")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.root, args.output, args.archive), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"build_plugin: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
