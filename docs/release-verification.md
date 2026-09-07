# Independent Release Verification — Orchestrate 2.0.0-rc.1

- **Date:** 2026-09-03
- **Role:** independent release/package verifier; no implementation changes made
- **Candidate root:** `/home/ricardo/orchestrate`
- **Observed Git HEAD:** `848640d04a8ca973a8d9dff16602152e3e49b31b`
- **Environment:** Python 3.12.3; Linux 7.0.0-30-generic x86_64
- **Verdict:** **REJECT**

The generated plugin archive is structurally valid, deterministic for the current filesystem state, installable in the isolated smoke harness, and successfully rolls back to the sentinel prior version. It is not releasable: the canonical source layout is uncommitted, the local aggregate gate omits blocking release conditions, current documentation is semantically stale, no CI result is attached, and license/release notes are absent.

## Gate and backlog verdicts

| ID | Result | Direct evidence and reason |
| --- | --- | --- |
| QG-01 | PASS | The official `quick_validate.py` exited 0 with `Skill is valid!`; the repository validator also passed with 0 errors and 0 warnings. |
| QG-02 | FAIL | `git status --porcelain=v1` is not clean: eight tracked files under `orchestrate/` are deleted and fourteen root entries are untracked. ADR-0001 documents the intended root layout, but HEAD does not contain it. |
| QG-03 | PASS | The deterministic skill/docs validators exited 0; JSON metadata, YAML, SVGs, and internal links passed their current checks. |
| QG-07 | FAIL | The generated local report says `passed: true`, but its command set does not check Git cleanliness, release notes/license, release provenance, or live CI results. It therefore cannot trace 100% of blocking release criteria to current checks. |
| QG-11 | FAIL | Mechanical ID/link validation passes, but `docs/index.md` still says the transformation is unimplemented and that evals and CI are absent, contradicting the current tree. |
| QG-12 | FAIL | `VERSION`, an archive, and an isolated rollback procedure exist and pass, but release notes are absent; the artifact is not tied to a committed source state. |
| ORC-050 | FAIL | The matrix distinguishes local surfaces from client smokes that are pending, but supplies no tested Codex client versions/results. No Codex CLI, IDE, or ChatGPT desktop invocation was executed. |
| ORC-051 | FAIL | Two local builds match byte-for-byte and contain only the allowlisted 17 files, but blocking gates are not green, the source is uncommitted, and a workflow definition is present without a current CI run result. |
| ORC-052 | REJECT | Independent archive install and isolated rollback were reproduced successfully, but the blocking release divergences above require rejection. |
| ORC-053 | FAIL | Package metadata and icons validate and archive installation passes; no license or release notes exist. No external publication or global installation was attempted. |

## Findings

### RV-001 — Candidate has no committed source provenance

- **Severity:** blocking
- **Confidence:** high
- **Affected:** QG-02, QG-12, ORC-051
- **Evidence:** HEAD tracks only the former nested `orchestrate/` source. The eight tracked source files appear deleted, while the canonical root implementation and its release machinery are untracked.
- **Impact:** a checkout of the recorded HEAD cannot reproduce the candidate archive. The archive hash identifies current bytes, not a committed release candidate.
- **Reproduction:** `git rev-parse HEAD`, `git status --porcelain=v1`, and `git diff --name-status`.

### RV-002 — Aggregate gate is green without covering all blocking release gates

- **Severity:** blocking
- **Confidence:** high
- **Affected:** QG-07, ORC-051
- **Evidence:** `.quality/release-verification-report.json` records nine passing local checks, but `scripts/quality_gate.py` has no Git-cleanliness, release-note/license, committed-provenance, or live-CI-result check.
- **Impact:** its top-level `passed: true` is a code/test/package result, not proof that every blocking release gate is green.
- **Reproduction:** `python3 scripts/quality_gate.py --report .quality/release-verification-report.json`, followed by inspection of the report and `scripts/quality_gate.py`.

### RV-003 — Release documentation is incomplete and semantically stale

- **Severity:** blocking
- **Confidence:** high
- **Affected:** QG-11, QG-12, ORC-053
- **Evidence:** `python3 scripts/validate_docs.py /home/ricardo/orchestrate` checks ID/link/DAG integrity and passes, but `docs/index.md` describes evals and CI as absent and the transformation as unimplemented. No `LICENSE*`, `CHANGELOG*`, or release-notes file exists outside generated output.
- **Impact:** consumers cannot reconcile the documented release state with the candidate, and the required release notes/license evidence is unavailable.
- **Reproduction:** `rg -n "transformação ainda não implementada|Evals comportamentais e CI: ausentes" docs/index.md`; search for release/license filenames with the command recorded below.

### RV-004 — Client compatibility remains unverified

- **Severity:** high for any claimed client distribution; non-blocking for isolated filesystem use
- **Confidence:** high
- **Affected:** ORC-050
- **Evidence:** `docs/compatibility.md` marks Codex CLI, Codex IDE extension, and ChatGPT desktop as contract-compatible with real smoke pending. No client versions or actual client smoke results are present.
- **Impact:** compatibility must not be presented as runtime support for those clients.
- **Reproduction:** inspect `docs/compatibility.md` and compare its support rule with the evidence below.

## Commands and results

All commands ran from `/home/ricardo/orchestrate`. Exit codes are recorded explicitly; expected negative-fixture rejection is not a release-check failure.

### Structural and integrated validation

```text
command: python3 /home/ricardo/.codex/skills/.system/skill-creator/scripts/quick_validate.py /home/ricardo/orchestrate
exit: 0
result: Skill is valid!

command: python3 scripts/quality_gate.py --report .quality/release-verification-report.json
exit: 0
result: validate_skill PASS (0 errors, 0 warnings); validate_docs PASS (0 errors); eval dataset PASS (40 cases); eval harness self-test PASS; 24 unit tests PASS; two builds PASS; plugin smoke/rollback PASS; deterministic archive PASS; aggregate passed=true.
note: the eval harness result uses its gold/self-test predictions and proves the harness, not behavior in an actual Codex client.

command: python3 scripts/validate_skill.py /home/ricardo/orchestrate
exit: 0
result (after adding this verification report): validate_skill PASS (0 errors, 0 warnings).

command: python3 scripts/validate_docs.py /home/ricardo/orchestrate
exit: 0
result (after adding this verification report): validate_docs PASS (0 errors).
```

The local quality report produced by that command had SHA-256 `95786e37450e3f136fdef8ea30c70f913583adb82d97d4944c1ae6269e5e06e3` before this report was added. It is an ignored local artifact, not a CI attestation.

### Git and layout

```text
command: git rev-parse HEAD
exit: 0
result: 848640d04a8ca973a8d9dff16602152e3e49b31b

command: git status --porcelain=v1
exit: 0
result: 8 tracked deletions under orchestrate/; 14 untracked root entries (.github/, .gitignore, SKILL.md, VERSION, agents/, assets/, config/, docs/, evals/, packaging/, references/, schemas/, scripts/, tests/).

command: git diff --name-status
exit: 0
result: the same 8 tracked nested source files are deleted; untracked root files are not represented by this diff.
```

ADR-0001 selects the repository root as canonical and correctly warns that Git will show the move until an authorized commit records it. This is a valid development state but fails the release gate's clean-worktree requirement. `dist/` and `.quality/` are ignored as documented generated artifacts.

### Deterministic build and artifact identity

```text
command: python3 scripts/build_plugin.py
exit: 0
result (run 1): version=2.0.0-rc.1; files=17; sha256=9b6719efeed796de5bbd64c478c04757e6d55a35021eaa80257026064e0d82f6
result (run 2): version=2.0.0-rc.1; files=17; sha256=9b6719efeed796de5bbd64c478c04757e6d55a35021eaa80257026064e0d82f6

command: sha256sum dist/orchestrate-2.0.0-rc.1.zip
exit: 0
result: 9b6719efeed796de5bbd64c478c04757e6d55a35021eaa80257026064e0d82f6  dist/orchestrate-2.0.0-rc.1.zip

command: stat -c 'bytes=%s mtime=%y' dist/orchestrate-2.0.0-rc.1.zip
exit: 0
result: bytes=23513

command: unzip -Z1 dist/orchestrate-2.0.0-rc.1.zip
exit: 0
result: 17 files under one orchestrate/ root: plugin manifest and icons, plus allowlisted SKILL.md, agent metadata, icons, budgets, seven references, state schema, and state validator.

commands:
  diff -qr agents dist/orchestrate/skills/orchestrate/agents
  diff -qr assets dist/orchestrate/skills/orchestrate/assets
  diff -qr references dist/orchestrate/skills/orchestrate/references
  cmp SKILL.md dist/orchestrate/skills/orchestrate/SKILL.md
  cmp config/budgets.json dist/orchestrate/skills/orchestrate/config/budgets.json
  cmp schemas/orchestration-state.schema.json dist/orchestrate/skills/orchestrate/schemas/orchestration-state.schema.json
  cmp scripts/validate_state.py dist/orchestrate/skills/orchestrate/scripts/validate_state.py
exit: 0
result: no differences.
```

The generated manifest identifies `orchestrate` version `2.0.0-rc.1`; its metadata, skill path, three prompts, and icon paths parsed successfully. The archive is locally deterministic, but because the source is untracked it is not reproducible from the recorded commit.

### Archive smoke, installed-artifact behavior, and rollback

```text
command: python3 scripts/smoke_plugin.py dist/orchestrate-2.0.0-rc.1.zip --source-root /home/ricardo/orchestrate
exit: 0
result: passed=true; installed name=orchestrate, version=2.0.0-rc.1, files=17; rollback_version=1.0.0.

command: python3 dist/orchestrate/skills/orchestrate/scripts/validate_state.py evals/fixtures/state-valid.json
exit: 0
result: validate_state: PASS (0 issues)

command: python3 dist/orchestrate/skills/orchestrate/scripts/validate_state.py evals/fixtures/state-invalid-overlap.json
exit: 1 (expected rejection)
result: OWNERSHIP_COLLISION detected for overlapping src/** and src/api/** ownership; validate_state FAIL (1 issue).
```

Rollback was exercised in a temporary isolated filesystem. The harness backed up a sentinel `orchestrate` 1.0.0 installation, installed and validated the archive, removed it, restored the backup, and verified the restored manifest. It did not mutate a real client installation and does not prove client-specific discovery or invocation.

### Missing release material

```text
command: find . -path './.git' -prune -o -path './dist' -prune -o -type f \( -iname 'LICENSE' -o -iname 'LICENSE.*' -o -iname 'CHANGELOG' -o -iname 'CHANGELOG.*' -o -iname '*release-notes*' -o -iname '*release_notes*' \) -print
exit: 0
result: no matching files.
```

## Supported and untested surfaces

| Surface | Verification in this run | Release interpretation |
| --- | --- | --- |
| Standalone local filesystem, Python 3.12.3 | Official structural validator, repository validators, harness self-test, and unit suite passed | Verified for the documented local validation workflow only |
| Local plugin archive | Deterministic build, manifest/tree validation, installed packaged state-validator checks, isolated install and rollback passed | Verified as a local artifact; no actual Codex client invocation |
| Codex CLI with skills | Not run; no client version recorded | Untested and not supported by this verdict |
| Codex IDE extension | Not run; no client version recorded | Untested and not supported by this verdict |
| ChatGPT desktop with skills | Not run; no client version recorded | Untested and not supported by this verdict |
| Personal marketplace | Not configured or touched | Unsupported pending separate authorization |
| Universal/external publication | Not attempted | Out of scope and unauthorized |

## Final verdict

**REJECT.** The archive mechanics and isolated rollback are sound, but QG-02, QG-07, QG-11, and QG-12 are blocking and currently fail. ORC-051 and ORC-053 are incomplete, and ORC-050 lacks real supported-client evidence. Reverification should use a committed clean candidate, current synchronized release documentation and notes/license, a gate dossier covering every blocking criterion, actual CI results, and client/version smoke evidence for every surface claimed as supported.
