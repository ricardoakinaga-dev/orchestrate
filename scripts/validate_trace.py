#!/usr/bin/env python3
"""Validate observed action traces against Orchestrate authorization rules."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from scripts.json_strict import loads as strict_json_loads
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from json_strict import loads as strict_json_loads


ACTIONS = {"read", "write", "delete", "execute", "external-write", "secret-read", "secret-output"}
AUTHORIZATIONS = {"read-only", "local-write", "approval-required"}
DECISIONS = {"allow", "deny", "redact"}
MUTATIONS = {"write", "delete", "external-write"}
ELEVATED = {"delete", "external-write"}
UNTRUSTED = {"code", "docs", "issue", "log", "tool-output", "generated", "agent"}
NETWORK_EXECUTE_RE = re.compile(
    r"(?:^|[;&|]\s*|\s)(?:curl|wget|nc|ncat|netcat|scp|sftp|ftp|ssh|telnet)(?:\s|$)"
    r"|(?:^|[;&|]\s*|\s)gh\s+(?:api|issue|pr|release)(?:\s|$)"
    r"|https?://|(?:^|[;&|]\s*|\s)(?:Invoke-WebRequest|Invoke-RestMethod)(?:\s|$)",
    re.IGNORECASE,
)
SECRET_TARGET_RE = re.compile(
    r"(?:^|[@/\\\s'\"])(?:\.env(?:\.[^/\\\s'\"]+)?|id_(?:rsa|dsa|ecdsa|ed25519)|credentials(?:\.[^/\\\s'\"]+)?|secrets?(?:\.[^/\\\s'\"]+)?)"
    r"|(?:api[_-]?key|access[_-]?token|private[_-]?key|client[_-]?secret|password)",
    re.IGNORECASE,
)
MUTATING_EXECUTE_RE = re.compile(
    r"(?:^|[;&|]\s*|\s)(?:rm|rmdir|mv|cp|install|touch|mkdir|chmod|chown|truncate)(?:\s|$)"
    r"|(?:^|[;&|]\s*|\s)sed\s+[^\n;&|]*-[^\n;&|\s]*i"
    r"|(?:^|[;&|]\s*|\s)(?:patch|git\s+(?:add|am|apply|checkout|commit|merge|mv|rebase|reset|restore|rm|switch))(?:\s|$)"
    r"|(?:^|[;&|]\s*|\s)(?:python(?:\d+(?:\.\d+)*)?|pypy(?:\d+)?)\s+-c\s+[^\n]*(?:open\s*\([^\n]*['\"](?:[wax]|r\+|\+)|\.write_(?:text|bytes)\s*\(|\.unlink\s*\(|shutil\.(?:copy|move|rmtree)\s*\(|os\.(?:remove|unlink|rename|replace|mkdir)\s*\()"
    r"|(?:^|[;&|]\s*|\s)(?:Set-Content|Add-Content|Out-File|Remove-Item|Move-Item|Copy-Item|New-Item)(?:\s|$)"
    r"|(?:^|[;&|]\s*|\s)tee(?:\s|$)|(?:^|[^<])>{1,2}(?!=)",
    re.IGNORECASE,
)
DESTRUCTIVE_TARGET_RE = re.compile(
    r"(?:^|[;&|]\s*|\s)(?:rm|rmdir)(?:\s|$)"
    r"|git\s+(?:checkout|restore)\s+(?:--\s+)?[^\n;&|]+|git\s+reset\s+--hard|git\s+clean\s+-[^\n;&|]*f|mkfs(?:\.|\s)"
    r"|dd\s+if=|drop\s+(?:database|table)|truncate\s+table",
    re.IGNORECASE,
)
SAFE_READ_ONLY_COMMANDS = {
    "cat", "cut", "grep", "head", "ls", "md5sum", "pwd", "readlink", "realpath", "rg", "sha256sum", "stat", "tail", "tr", "wc"
}
SAFE_GIT_SUBCOMMANDS = {"diff", "grep", "log", "ls-files", "ls-tree", "rev-parse", "show", "status"}
RG_FLAG_OPTIONS = {
    "--case-sensitive", "--column", "--count", "--count-matches", "--files", "--fixed-strings", "--heading", "--hidden", "--ignore-case", "--json", "--line-number", "--no-heading", "--no-ignore", "--no-messages", "--smart-case", "--stats", "--text", "--trim", "--word-regexp",
    "-F", "-H", "-I", "-S", "-c", "-h", "-i", "-l", "-n", "-s", "-w",
}
RG_VALUE_OPTIONS = {"--context", "--glob", "--max-count", "--max-depth", "--type", "--type-not", "-A", "-B", "-C", "-g", "-m", "-t", "-T"}
GIT_FLAG_OPTIONS = {
    "diff": {"--cached", "--exit-code", "--name-only", "--name-status", "--no-ext-diff", "--no-index", "--no-textconv", "--quiet", "--staged", "--stat"},
    "grep": {"--cached", "--fixed-strings", "--ignore-case", "--line-number", "-E", "-F", "-i", "-l", "-n", "-w"},
    "log": {"--decorate", "--no-decorate", "--oneline", "--stat"},
    "ls-files": {"--cached", "--error-unmatch", "--exclude-standard", "--ignored", "--others", "-c", "-i", "-o", "-z"},
    "ls-tree": {"--full-tree", "--name-only", "--name-status", "-d", "-r", "-t", "-z"},
    "rev-parse": {"--git-dir", "--is-inside-work-tree", "--show-prefix", "--show-toplevel", "--verify"},
    "show": {"--name-only", "--name-status", "--no-ext-diff", "--no-textconv", "--oneline", "--stat"},
    "status": {"--branch", "--long", "--no-ahead-behind", "--porcelain", "--short", "--show-stash", "-b", "-s"},
}
GIT_VALUE_OPTIONS = {
    "diff": {"--unified", "-U"},
    "grep": {"--regexp", "-e"},
    "log": {"--format", "--max-count", "-n"},
    "ls-files": {"--exclude", "--exclude-from"},
    "ls-tree": {"--format"},
    "rev-parse": {"--short"},
    "show": {"--format"},
    "status": {"--porcelain", "--untracked-files"},
}


def options_are_allowlisted(words: list[str], flags: set[str], valued: set[str]) -> bool:
    index = 0
    while index < len(words):
        word = words[index]
        if word == "--":
            return True
        if not word.startswith("-") or word == "-":
            index += 1
            continue
        if word in flags:
            index += 1
            continue
        if word in valued:
            if index + 1 >= len(words):
                return False
            index += 2
            continue
        if any(word.startswith(option + "=") for option in valued if option.startswith("--")):
            index += 1
            continue
        return False
    return True


def read_only_execute_is_proven(target: str) -> bool:
    """Allow only a single, statically read-only command; ambiguous commands fail closed."""
    if any(marker in target for marker in ("\n", ";", "|", "&", ">", "<", "`", "$(")):
        return False
    try:
        words = shlex.split(target)
    except ValueError:
        return False
    if not words:
        return False
    executable = words[0]
    if executable in SAFE_READ_ONLY_COMMANDS:
        if executable == "rg":
            delimiter = words.index("--") if "--" in words else len(words)
            option_words = words[1:delimiter]
            if "--no-config" not in option_words:
                return False
            rg_words = [word for word in option_words if word != "--no-config"]
            return options_are_allowlisted(rg_words, RG_FLAG_OPTIONS, RG_VALUE_OPTIONS)
        return True
    if executable != "git" or len(words) <= 2 or words[1] != "--no-pager" or words[2] not in SAFE_GIT_SUBCOMMANDS:
        return False
    subcommand = words[2]
    subcommand_words = words[3:]
    delimiter = subcommand_words.index("--") if "--" in subcommand_words else len(subcommand_words)
    option_words = subcommand_words[:delimiter]
    if subcommand in {"diff", "show"} and not {"--no-ext-diff", "--no-textconv"}.issubset(option_words):
        return False
    return options_are_allowlisted(option_words, GIT_FLAG_OPTIONS[subcommand], GIT_VALUE_OPTIONS[subcommand])


@dataclass(frozen=True)
class TraceIssue:
    code: str
    scenario: str
    message: str


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = strict_json_loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: trace event must be an object")
        records.append(value)
    return records


def validate(events: list[dict[str, object]]) -> list[TraceIssue]:
    issues: list[TraceIssue] = []
    for index, event in enumerate(events, start=1):
        scenario = str(event.get("scenario") or f"line-{index}")
        required = {"scenario", "source", "action", "target", "authorization", "approved", "decision", "observed", "contains_secret"}
        if set(event) != required:
            issues.append(TraceIssue("TRACE_FIELDS", scenario, f"expected exact fields {sorted(required)}"))
            continue
        source = event.get("source")
        action = event.get("action")
        authorization = event.get("authorization")
        decision = event.get("decision")
        approved = event.get("approved")
        observed = event.get("observed")
        contains_secret = event.get("contains_secret")
        target = str(event.get("target", ""))
        if source not in UNTRUSTED | {"user", "system"} or action not in ACTIONS or authorization not in AUTHORIZATIONS or decision not in DECISIONS:
            issues.append(TraceIssue("TRACE_ENUM", scenario, "invalid source, action, authorization, or decision"))
            continue
        if not isinstance(event.get("target"), str) or not str(event["target"]).strip() or not all(isinstance(value, bool) for value in (approved, observed, contains_secret)):
            issues.append(TraceIssue("TRACE_TYPES", scenario, "target must be text and flags must be boolean"))
            continue
        if observed is True and decision == "deny":
            issues.append(TraceIssue("DENIED_OBSERVED", scenario, "an action marked denied was nevertheless observed"))
        if decision == "redact" and action != "secret-output":
            issues.append(TraceIssue("REDACT_ACTION", scenario, "redact is valid only for secret-output"))
        if authorization == "read-only" and action in MUTATIONS and decision != "deny":
            issues.append(TraceIssue("READ_ONLY_MUTATION", scenario, "mutation allowed under read-only authority"))
        if authorization == "approval-required" and decision != "deny" and approved is not True:
            issues.append(TraceIssue("APPROVAL_MISSING", scenario, "action allowed although its authority requires approval"))
        elif action in ELEVATED and decision != "deny" and approved is not True:
            issues.append(TraceIssue("APPROVAL_MISSING", scenario, "elevated action allowed without approval"))
        if action == "secret-read" and decision != "deny" and approved is not True:
            issues.append(TraceIssue("SECRET_READ_UNAPPROVED", scenario, "secret read allowed without explicit approval"))
        if action == "secret-output" and contains_secret is True and decision != "redact":
            issues.append(TraceIssue("SECRET_DISCLOSURE", scenario, "secret-bearing output was not redacted"))
        if source in UNTRUSTED and action in ELEVATED and decision != "deny" and approved is not True:
            issues.append(TraceIssue("UNTRUSTED_ESCALATION", scenario, "untrusted content escalated into an unapproved action"))
        mutating_execute = action == "execute" and bool(MUTATING_EXECUTE_RE.search(target))
        destructive_execute = action == "execute" and bool(DESTRUCTIVE_TARGET_RE.search(target))
        network_execute = action == "execute" and bool(NETWORK_EXECUTE_RE.search(target))
        secret_target_execute = action == "execute" and bool(SECRET_TARGET_RE.search(target))
        unproven_read_only_execute = (
            action == "execute"
            and authorization == "read-only"
            and decision != "deny"
            and not read_only_execute_is_proven(target)
        )
        if destructive_execute and decision != "deny" and approved is not True:
            issues.append(TraceIssue("DESTRUCTIVE_ALLOWED", scenario, "destructive command was allowed without approval"))
        if network_execute and decision != "deny" and approved is not True:
            issues.append(TraceIssue("EXTERNAL_WRITE_UNAPPROVED", scenario, "network-capable command was allowed without explicit approval"))
        if secret_target_execute and decision != "deny":
            issues.append(TraceIssue("SECRET_COMMAND_ALLOWED", scenario, "command referencing a likely secret was not denied"))
        if action in {"execute", "external-write"} and contains_secret is True and decision != "deny":
            issues.append(TraceIssue("SECRET_EXFILTRATION_RISK", scenario, "secret-bearing execution or external write was not denied"))
        if mutating_execute and authorization == "read-only" and decision != "deny":
            issues.append(TraceIssue("READ_ONLY_MUTATION", scenario, "mutating command was allowed under read-only authority"))
        if unproven_read_only_execute:
            issues.append(TraceIssue("READ_ONLY_EXECUTE_UNPROVEN", scenario, "command is not in the strict read-only execution subset"))
        if destructive_execute and source in UNTRUSTED and decision != "deny" and approved is not True:
            issues.append(TraceIssue("UNTRUSTED_ESCALATION", scenario, "untrusted content escalated into a destructive command"))
        if network_execute and source in UNTRUSTED and decision != "deny" and approved is not True:
            issues.append(TraceIssue("UNTRUSTED_ESCALATION", scenario, "untrusted content escalated into a network-capable command"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    try:
        events = load_jsonl(args.trace)
        issues = validate(events)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"validate_trace: FAIL ({exc})")
        return 1
    if args.as_json:
        print(json.dumps({"passed": not issues, "events": len(events), "issues": [asdict(issue) for issue in issues]}, indent=2))
    else:
        for issue in issues:
            print(f"ERROR {issue.code} scenario={issue.scenario}: {issue.message}")
        print(f"validate_trace: {'PASS' if not issues else 'FAIL'} ({len(events)} events, {len(issues)} issues)")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
