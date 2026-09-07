#!/usr/bin/env python3
"""Smoke-test a built plugin archive and an isolated backup/rollback cycle."""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

try:
    from scripts.build_plugin import expected_plugin_files, plugin_source_files, rendered_manifest_bytes
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from build_plugin import expected_plugin_files, plugin_source_files, rendered_manifest_bytes
    from json_strict import loads as strict_json_loads


def safe_members(bundle: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = bundle.infolist()
    if not members:
        raise ValueError("archive is empty")
    names: set[str] = set()
    total_uncompressed = 0
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or member.is_dir():
            raise ValueError(f"unsafe archive member {member.filename!r}")
        if member.filename in names:
            raise ValueError(f"duplicate archive member {member.filename!r}")
        unix_mode = member.external_attr >> 16
        file_type = stat.S_IFMT(unix_mode)
        if stat.S_ISLNK(unix_mode) or (file_type and file_type != stat.S_IFREG):
            raise ValueError(f"non-regular archive member {member.filename!r}")
        if member.flag_bits & 0x1:
            raise ValueError(f"encrypted archive member {member.filename!r}")
        if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ValueError(f"unsupported compression for archive member {member.filename!r}")
        if member.file_size > 2_000_000:
            raise ValueError(f"oversized archive member {member.filename!r}")
        total_uncompressed += member.file_size
        if total_uncompressed > 10_000_000:
            raise ValueError("archive expands beyond the 10 MB safety limit")
        names.add(member.filename)
    return members


def validate_tree(plugin: Path, source_root: Path | None = None) -> dict[str, object]:
    actual_files = {path.relative_to(plugin).as_posix() for path in plugin.rglob("*") if path.is_file()}
    expected_files = expected_plugin_files()
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        unexpected = sorted(actual_files - expected_files)
        raise ValueError(f"plugin membership mismatch (missing={missing}, unexpected={unexpected})")
    manifest_path = plugin / ".codex-plugin" / "plugin.json"
    manifest = strict_json_loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("plugin manifest must be a JSON object")
    if manifest.get("name") != "orchestrate":
        raise ValueError("plugin name mismatch")
    skill = plugin / "skills" / "orchestrate"
    if source_root is not None:
        for packaged, canonical in plugin_source_files().items():
            if (source_root / canonical).read_bytes() != (plugin / packaged).read_bytes():
                raise ValueError(f"packaged {packaged} differs from canonical {canonical}")
        if manifest_path.read_bytes() != rendered_manifest_bytes(source_root):
            raise ValueError("packaged manifest differs from canonical rendered manifest")
    if manifest.get("license") != "UNLICENSED":
        raise ValueError("plugin license status mismatch")
    return {"name": manifest["name"], "version": manifest.get("version"), "files": len([path for path in plugin.rglob("*") if path.is_file()])}


def smoke(archive: Path, source_root: Path | None = None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="orchestrate-smoke-") as temporary:
        temp = Path(temporary)
        extracted = temp / "extracted"
        with zipfile.ZipFile(archive) as bundle:
            members = safe_members(bundle)
            expected_members = {f"orchestrate/{entry}" for entry in expected_plugin_files()}
            actual_members = {member.filename for member in members}
            if actual_members != expected_members:
                missing = sorted(expected_members - actual_members)
                unexpected = sorted(actual_members - expected_members)
                raise ValueError(f"archive membership mismatch (missing={missing}, unexpected={unexpected})")
            bundle.extractall(extracted, members=members)
        roots = [path for path in extracted.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise ValueError("archive must contain exactly one plugin root")
        candidate = roots[0]
        installed = validate_tree(candidate, source_root)

        active_parent = temp / "active"
        active = active_parent / "orchestrate"
        backup = temp / "backup" / "orchestrate"
        (active / ".codex-plugin").mkdir(parents=True)
        prior = {"name": "orchestrate", "version": "1.0.0", "description": "rollback sentinel"}
        (active / ".codex-plugin" / "plugin.json").write_text(json.dumps(prior), encoding="utf-8")
        shutil.copytree(active, backup)
        shutil.rmtree(active)
        shutil.copytree(candidate, active)
        validate_tree(active, source_root)
        shutil.rmtree(active)
        shutil.copytree(backup, active)
        restored = strict_json_loads((active / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        if restored != prior:
            raise ValueError("rollback did not restore the prior plugin")
        return {"passed": True, "installed": installed, "rollback_version": restored["version"]}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--source-root", type=Path, default=root)
    args = parser.parse_args()
    try:
        print(json.dumps(smoke(args.archive.resolve(), args.source_root.resolve()), indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f"smoke_plugin: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
