#!/usr/bin/env python3
"""Validate the Orchestrate source package without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SECRET_PATTERNS = (
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("OPENAI_TOKEN", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
)
SENSITIVE_FILENAMES = {".env", "id_dsa", "id_ed25519", "id_rsa"}
PLACEHOLDER_RE = re.compile(r"\$\{[A-Z][A-Z0-9_]*\}|\{\{[^{}]+\}\}|<TODO>|\b(?:TODO|FIXME|TBD)\b")


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    path: str
    severity: str = "error"


def load_json_strict(text: str) -> object:
    return strict_json_loads(text)


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 4 or lines[0] != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("SKILL.md frontmatter is not closed") from exc
    metadata: dict[str, str] = {}
    for number, line in enumerate(lines[1:closing], start=2):
        if not line.strip():
            continue
        key, separator, raw = line.partition(":")
        if not separator or not key.strip() or not raw.strip():
            raise ValueError(f"invalid frontmatter entry at line {number}")
        normalized_key = key.strip()
        if normalized_key in metadata:
            raise ValueError(f"duplicate frontmatter key {normalized_key!r} at line {number}")
        metadata[normalized_key] = raw.strip().strip('"')
    return metadata, "\n".join(lines[closing + 1 :])


def parse_simple_yaml(path: Path) -> dict[str, object]:
    """Parse the mapping/scalar YAML subset used by agents/openai.yaml."""
    root: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(-1, root)]
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" in line:
            raise ValueError(f"tabs are not allowed at line {number}")
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2:
            raise ValueError(f"indentation must use multiples of two at line {number}")
        key, separator, raw = line.strip().partition(":")
        if not separator or not key:
            raise ValueError(f"invalid mapping at line {number}")
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if key in parent:
            raise ValueError(f"duplicate key {key!r} at line {number}")
        raw = raw.strip()
        if not raw:
            value: object = {}
            parent[key] = value
            stack.append((indent, value))
        elif raw in {"true", "false"}:
            parent[key] = raw == "true"
        elif raw.startswith('"') and raw.endswith('"'):
            parent[key] = load_json_strict(raw)
        else:
            raise ValueError(f"string values must be quoted at line {number}")
    return root


def check_markdown(root: Path, path: Path) -> list[Finding]:
    findings: list[Finding] = []
    relative = str(path.relative_to(root))
    text = path.read_text(encoding="utf-8")
    if any(line.endswith((" ", "\t")) for line in text.splitlines()):
        findings.append(Finding("MD_TRAILING_SPACE", "trailing whitespace", relative))
    if sum(1 for line in text.splitlines() if line.startswith("```")) % 2:
        findings.append(Finding("MD_FENCE", "unbalanced fenced code block", relative))
    for raw_target in LINK_RE.findall(text):
        target = raw_target.split("#", 1)[0]
        if not target or re.match(r"^(?:https?|mailto|codex):", target):
            continue
        resolved = (path.parent / unquote(target)).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            findings.append(Finding("LINK_ESCAPE", f"link escapes package: {raw_target}", relative))
            continue
        if not resolved.exists():
            findings.append(Finding("LINK_BROKEN", f"missing link target: {raw_target}", relative))
    return findings


def check_secrets(root: Path) -> list[Finding]:
    """Reject high-confidence credential material without echoing its value."""
    findings: list[Finding] = []
    excluded = {".git", ".quality", "__pycache__", "dist"}
    for path in sorted(root.rglob("*")):
        if any(part in excluded for part in path.parts):
            continue
        relative = str(path.relative_to(root))
        if path.is_symlink():
            findings.append(Finding("UNSAFE_SYMLINK", "package files must not be symlinks", relative))
            continue
        if not path.is_file():
            continue
        if path.name in SENSITIVE_FILENAMES or path.name.endswith((".p12", ".pfx")):
            findings.append(Finding("SENSITIVE_FILE", "credential-bearing filename is not allowed", relative))
            continue
        try:
            payload = path.read_bytes()
        except OSError as exc:
            findings.append(Finding("SECRET_SCAN_READ", str(exc), relative))
            continue
        if len(payload) > 2_000_000 or b"\x00" in payload:
            continue
        text = payload.decode("utf-8", errors="ignore")
        for code, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(Finding(code, "high-confidence secret material detected; value suppressed", relative))
    return findings


def check_placeholders(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    roots = [root / "SKILL.md", root / "agents", root / "references", root / "config", root / "schemas", root / "packaging"]
    for entry in roots:
        paths = [entry] if entry.is_file() else sorted(path for path in entry.rglob("*") if path.is_file()) if entry.exists() else []
        for path in paths:
            if path.is_symlink():
                continue
            relative = str(path.relative_to(root))
            matches = PLACEHOLDER_RE.findall(path.read_text(encoding="utf-8"))
            if relative == "packaging/plugin.template.json":
                matches = [match for match in matches if match != "${VERSION}"]
            for _match in matches:
                findings.append(Finding("PLACEHOLDER", "unresolved placeholder detected; value suppressed", relative))
    return findings


def validate(root: Path) -> tuple[list[Finding], list[Finding]]:
    root = root.resolve()
    errors: list[Finding] = []
    warnings: list[Finding] = []
    skill_path = root / "SKILL.md"
    if not skill_path.is_file() or skill_path.is_symlink():
        return [Finding("SKILL_MISSING", "SKILL.md is required", "SKILL.md")], warnings

    try:
        metadata, body = parse_frontmatter(skill_path)
    except ValueError as exc:
        return [Finding("FRONTMATTER", str(exc), "SKILL.md")], warnings

    name = metadata.get("name", "")
    description = metadata.get("description", "")
    if not NAME_RE.fullmatch(name) or len(name) > 64:
        errors.append(Finding("NAME", "name must be lowercase hyphen-case and at most 64 characters", "SKILL.md"))
    if root.name != name:
        warnings.append(Finding("FOLDER_NAME", f"folder {root.name!r} differs from skill name {name!r}", ".", "warning"))
    if not description:
        errors.append(Finding("DESCRIPTION", "description is required", "SKILL.md"))
    elif len(description) > 1024:
        errors.append(Finding("DESCRIPTION", "description exceeds 1024 characters", "SKILL.md"))
    elif len(description) > 500:
        warnings.append(Finding("DESCRIPTION_LONG", "description exceeds the preferred 500-character routing budget", "SKILL.md", "warning"))
    if not body.strip():
        errors.append(Finding("BODY", "skill instructions are empty", "SKILL.md"))

    yaml_path = root / "agents" / "openai.yaml"
    try:
        if yaml_path.is_symlink():
            raise ValueError("agents/openai.yaml must not be a symlink")
        yaml_data = parse_simple_yaml(yaml_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(Finding("OPENAI_YAML", str(exc), "agents/openai.yaml"))
        yaml_data = {}
    interface = yaml_data.get("interface", {})
    policy = yaml_data.get("policy", {})
    if not isinstance(interface, dict) or not isinstance(policy, dict):
        errors.append(Finding("OPENAI_YAML_SHAPE", "interface and policy must be mappings", "agents/openai.yaml"))
    else:
        required = {"display_name", "short_description", "default_prompt"}
        missing = sorted(required - interface.keys())
        if missing:
            errors.append(Finding("OPENAI_YAML_FIELDS", f"missing interface fields: {', '.join(missing)}", "agents/openai.yaml"))
        short = interface.get("short_description", "")
        if isinstance(short, str) and not 25 <= len(short) <= 64:
            errors.append(Finding("SHORT_DESCRIPTION", "short_description must contain 25-64 characters", "agents/openai.yaml"))
        prompt = interface.get("default_prompt", "")
        if isinstance(prompt, str) and f"${name}" not in prompt:
            errors.append(Finding("DEFAULT_PROMPT", f"default_prompt must mention ${name}", "agents/openai.yaml"))
        if policy.get("allow_implicit_invocation") is not True:
            errors.append(Finding("INVOCATION_POLICY", "implicit invocation must remain enabled", "agents/openai.yaml"))
        for field in ("icon_small", "icon_large"):
            value = interface.get(field)
            if value:
                unresolved_icon = root / str(value)
                icon = unresolved_icon.resolve()
                try:
                    icon.relative_to(root)
                except ValueError:
                    errors.append(Finding("ICON_ESCAPE", f"{field} escapes package", "agents/openai.yaml"))
                else:
                    if unresolved_icon.is_symlink():
                        errors.append(Finding("ICON_SYMLINK", f"{field} target must not be a symlink", "agents/openai.yaml"))
                    elif not icon.is_file():
                        errors.append(Finding("ICON_MISSING", f"{field} target does not exist", "agents/openai.yaml"))

    for markdown in sorted(root.rglob("*.md")):
        if any(part in {".git", "dist", ".quality"} for part in markdown.parts):
            continue
        if markdown.is_symlink():
            continue
        errors.extend(check_markdown(root, markdown))

    json_paths = [path for folder in ("config", "schemas", "packaging") for path in (root / folder).rglob("*.json")]
    for path in sorted(json_paths):
        if path.is_symlink():
            continue
        try:
            load_json_strict(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(Finding("JSON", str(exc), str(path.relative_to(root))))

    for svg in sorted((root / "assets").glob("*.svg")):
        if svg.is_symlink():
            continue
        try:
            ET.parse(svg)
        except ET.ParseError as exc:
            errors.append(Finding("SVG", str(exc), str(svg.relative_to(root))))

    version_path = root / "VERSION"
    if version_path.is_file():
        version = version_path.read_text(encoding="utf-8").strip()
        if not SEMVER_RE.fullmatch(version):
            errors.append(Finding("VERSION", "VERSION must use strict semantic versioning", "VERSION"))
    else:
        errors.append(Finding("VERSION_MISSING", "VERSION is required", "VERSION"))
    errors.extend(check_placeholders(root))
    errors.extend(check_secrets(root))
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    errors, warnings = validate(args.root)
    if args.as_json:
        print(json.dumps({"passed": not errors, "errors": [asdict(item) for item in errors], "warnings": [asdict(item) for item in warnings]}, indent=2))
    else:
        for item in [*errors, *warnings]:
            print(f"{item.severity.upper()} {item.code} {item.path}: {item.message}")
        print(f"validate_skill: {'PASS' if not errors else 'FAIL'} ({len(errors)} errors, {len(warnings)} warnings)")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
