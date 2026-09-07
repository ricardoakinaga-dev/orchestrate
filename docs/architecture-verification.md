# Independent Architecture and Backlog Verification

- **Date:** 2026-09-03
- **Scope:** current workspace against `ORC-001`–`ORC-053`, `QG-04`, `QG-08`, `QG-09`, `QG-10`, and the three-mode topology contract
- **Role:** independent verifier; no product repair performed
- **Verdict:** **REJECT** for AAA/release acceptance

The current source is structurally healthy and its v2 blind routing score clears the numeric routing thresholds. Release acceptance is nevertheless unsupported: the Git snapshot is not clean or reproducible, the CI gate exercises gold labels rather than live behavior, single-versus-multi value and human calibration have not been measured, real client compatibility is pending, and the topology scorer permits an invalid `direct` result that delegates.

`PASS` below means all item-local criteria have current direct evidence. `CONDITIONAL` means useful implementation and evidence exist but the item is not accepted. `FAIL` means a required criterion is absent or contradicted. `NOT RUN` means the required study was not executed. Item-local status does not override backlog dependencies; a downstream item cannot make a milestone complete while its prerequisites fail.

## Evidence executed

| Ref | Check | Result |
| --- | --- | --- |
| E1 | `PYTHONDONTWRITEBYTECODE=1 python3 scripts/quality_gate.py` | `PASS`; 24 unit tests and all 9 current local checks passed, including two deterministic builds, archive smoke, and isolated rollback. Temporary build SHA-256 was `9b6719efeed796de5bbd64c478c04757e6d55a35021eaa80257026064e0d82f6`. |
| E2 | `python3 scripts/run_evals.py score --predictions evals/results/live-v2-run-{1,2,3}.jsonl --min-runs 3` | `PASS`; 40 cases/120 predictions, activation `1.000`, false-positive rate `0`, mode `0.983333`, delegation `1.000`, authorization `1.000`, critical violations `0`. |
| E3 | In-memory known-bad probe: change `ACT-003` to `direct` plus `delegate=true`, then call `validate_predictions` and `score` | `FAIL` of the contract: validation returned `[]` and the aggregate still returned `passed=true` with delegation accuracy `0.975`. |
| E4 | `git status --short`, `git rev-parse HEAD`, `git ls-files` | `FAIL` for release hygiene: HEAD is `848640d04a8ca973a8d9dff16602152e3e49b31b`; eight old `orchestrate/` files are deleted, the new root product is untracked, and HEAD tracks only 8 files. |
| E5 | `python3 scripts/smoke_plugin.py dist/orchestrate-2.0.0-rc.1.zip --source-root .` plus `sha256sum` | `PASS`; current 17-file archive installs in the isolated simulator, matches canonical `SKILL.md`, rolls back to the sentinel, and has the same SHA-256 as E1. |
| E6 | Full workspace read/hash inventory excluding `.git` | 89 files read before this report: 75 UTF-8 files and 14 binary artifacts (`.zip` and bytecode). Source, tests, datasets, results, schemas, package contents, workflow, and documentation were inspected. |

The workspace changed during the audit when the source/distribution was refreshed. E1–E5 were rerun against the final observed post-refresh snapshot. This is sufficient for a snapshot verdict but not a stable release chain of custody.

## Acceptance matrix

| ID | Status | Implemented tooling/artifact | Executed evidence and remaining gap |
| --- | --- | --- | --- |
| ORC-001 | FAIL | Root layout is selected in the ADR; build allowlist emits one skill copy. | E1/E5 validate the root and package, but E4 is dirty and the approved relocation is absent from HEAD. |
| ORC-002 | PASS | [ADR-0001](adr/0001-layout-and-distribution.md) records context, alternatives, root choice, local/plugin paths, consequences, and excludes publication. | Static inspection confirms no external publication action in the item. |
| ORC-003 | FAIL | Workflow, structural validator, and negative unit tests exist. | E1 passes, but `validate_skill.py` has no placeholder check, there is no failing fixture for every listed critical rule, and Actions are major-tag pinned rather than immutable/verified. |
| ORC-004 | CONDITIONAL | [baseline-v1.json](../evals/baseline-v1.json) preserves commit, corpus counts/hash context, date, and static outcome separately from later results. | Runtime/evaluation environment and configuration are not captured sufficiently to reproduce behavior. |
| ORC-010 | FAIL | Rubric and thresholds cover activation, mode, delegation, authorization, and critical safety veto. | Decomposition, ownership, evidence quality, and final-result quality lack scored dimensions/anchors; no three-role review sign-off is recorded. |
| ORC-011 | FAIL | Forty cases include explicit, implicit, negative, near-boundary prompts and report false positives. | There is no documented development/held-out provenance and only exact normalized duplicate detection, not semantic duplicate detection. |
| ORC-012 | FAIL | Expected modes, rationales, boundary tags, and confusion matrix exist. | Required small-multifile and large-coupled coverage is not demonstrated; the Scout/Multi boundary is observably ambiguous. |
| ORC-013 | FAIL | Prompts cover implementation, architecture, diagnosis, research, review, and verification. | They are routing-label cases, not executable scenarios with produced artifacts, observable product criteria, and a single-agent task baseline. |
| ORC-014 | CONDITIONAL | Ten critical-tag predictions cover secrets, injection, destructive commands, scope, and external writes across code/docs/log/tool-output-like prompts. | E2 reports zero self-declared critical violations, but no action-level adversarial execution or standalone threat matrix proves behavior at the real side-effect boundary. |
| ORC-015 | FAIL | Every category has English and Portuguese cases, and scorecards segment locale/tags. | The one `long-context` case is a short prompt rather than long/compacted context, and the `typo`-tagged prompt does not demonstrate a typo robustness test. |
| ORC-016 | FAIL | JSONL harness validates, repeats, scores, segments, and preserves individual predictions. | It does not capture runtime configuration, tokens, latency, actual agents, retries, or calculable cost; partial task failures are not modeled as required. |
| ORC-017 | FAIL | v1 and v2 routing scorecards exist. | They compare prompt versions/classifications, not single-agent versus multi-agent task execution; quality, cost, latency dispersion, environment parity, and owner signatures are absent. |
| ORC-020 | PASS | `SKILL.md` makes material value, specificability, verifiability, safe partition, and authorization mandatory and includes cost/risk/capacity considerations. | E2 clears routing thresholds with no critical regression. |
| ORC-021 | PASS | Direct/Scout/Multi topology is explicitly orthogonal to read-only/local-write/approval-required authorization. | E2 includes Direct, Scout, and Multi read-only cases and small read-only negative/direct cases. |
| ORC-022 | CONDITIONAL | Agent return template, workflow, and ledger schema use concise evidence digests; prose requires sanitized full logs on demand and blocks state promotion without evidence. | E1 lacks the required large-log and fake-secret digest tests; `IMPLEMENTED` enforcement remains prose rather than ledger validation. |
| ORC-023 | CONDITIONAL | A short mandatory brief, optional risk extensions, ownership, authorization, and self-contained return contract exist. | No token/performance comparison against the previous template was executed. |
| ORC-024 | FAIL | Shared controls are split into routed references; current nine-file instruction corpus is 27,267 bytes/3,697 words versus baseline 33,589 bytes/4,701 words. | No canonical-control inventory or small-group ablation proves non-regression; byte reduction is about 18.8%, and broad v1/v2 change attribution is unavailable. |
| ORC-025 | CONDITIONAL | `config/budgets.json` sets mode-based agent/retry limits, precedence, risk gates, and marginal-value stop conditions without model names. | No numeric token/time/cost ceiling exists per task class, and limit scenarios do not cover all budget dimensions. |
| ORC-026 | FAIL | v1/v2 routing results provide a before/after signal. | There is no paired one-change-at-a-time ablation matrix or documented identical environment; the rewrite cannot attribute impact by change. |
| ORC-030 | PASS | `security.md` treats repository/external/tool content as data, requires command inspection, minimizes secrets, and bounds side effects. | E1 exercises secret suppression/path safety and E2 gives 100% exact critical-tag routing with zero declared violation. |
| ORC-031 | PASS | State validator detects hierarchical path overlap, exact named-resource overlap, ownership escape, and blocks concurrent `RUNNING` owners with actionable codes. | E1 passes valid/invalid overlap fixtures; coverage is narrow but satisfies the present named examples. |
| ORC-032 | PASS | State schema/validator rejects invalid transitions, stale contracts, missing current required evidence, bad dependency state, and high findings on `DONE`. | E1 passes valid state and rejects transition/evidence/contract fixtures. |
| ORC-033 | FAIL | Recovery prose defines transient, specification, implementation, architecture/integration, and permission failures plus resume rules. | No report or deterministic tests cover all classes, retry history/limits, interruption, and filesystem reconciliation. |
| ORC-034 | PASS | This report is an independent, non-editing verification against original criteria and artifacts and gives a release-blocking verdict. | High release/topology gaps are not waived; this `REJECT` blocks acceptance rather than self-approving implementation. |
| ORC-040 | FAIL | Routing scorecards report success, dimensions, modes, categories, locales, and tags. | Tokens, latency, actual agent count, retries, rework, collisions, and explicit `BLOCKED`/`NOT RUN` outcomes are absent. |
| ORC-041 | NOT RUN | Rubric says human calibration is required. | No blind human labels, agreement study, divergence report, or approved calibration threshold exists. |
| ORC-042 | NOT RUN | v1/v2 artifacts exist but are not an ablation. | No frozen held-out, one-category-at-a-time prompt ablation or cost-qualified winning decision was executed. |
| ORC-043 | CONDITIONAL | Versioned mode/risk budgets define agent/retry limits, precedence, stop/escalation behavior, and avoid ephemeral model names. | Product-owner approval is not recorded and observable token/time/cost limits are missing. |
| ORC-050 | CONDITIONAL | [compatibility.md](compatibility.md) lists local, Codex CLI, IDE, desktop, plugin, marketplace, and publication surfaces and marks real client smoke pending. | Only local filesystem/plugin simulation ran; client versions, discovery, explicit/implicit invocation, and recovery were not executed. |
| ORC-051 | FAIL | E1/E5 prove deterministic current builds with version, manifest, allowlist, and hash. | E4 prevents reproduction from HEAD; blocking gates are not green, stored `.quality/report.json` is stale, and no immutable CI/release dossier exists. |
| ORC-052 | CONDITIONAL | E5 independently reproduces simulated archive install and isolated rollback; mismatch would fail. | Critical behavioral scenarios were not run through an installed real client, so release verification is incomplete. |
| ORC-053 | CONDITIONAL | Versioned plugin, coherent manifest, icons, deterministic ZIP, path-safe extraction, and artifact-based simulated install exist. | No license or release notes exist, and no approved external distribution or real-client installation was demonstrated. |

## Requested quality gates

| Gate | Status | Direct evidence |
| --- | --- | --- |
| QG-04 | PASS | E2 is a three-run blind score over 40 cases and meets `OBJ-01`/`OBJ-02`: activation `100%`, false positives `0%`, mode `98.33%`. This proves routing classification on this dataset, not product-task success. |
| QG-08 | FAIL | No same-task single-versus-multi experiment reports quality non-inferiority, median latency improvement, tokens, agents, or approved budget adherence. |
| QG-09 | FAIL | E5 proves only an isolated simulator. The compatibility matrix explicitly says real Codex CLI, IDE, and ChatGPT desktop smoke is pending. |
| QG-10 | NOT RUN | No human calibration or agreement artifact exists; automatic graders therefore cannot act as release authority. |

## Three-mode/topology consistency

**Status: FAIL.** Representation is consistent across `SKILL.md`, the rubric, schemas, dataset, and budget keys: all use `direct`, `scout-assisted`, and `multi-workstream`, with authorization orthogonal. Two architectural defects remain:

1. Scout and Multi are not mutually exclusive for independent read-only research. `ACT-010` expects Multi for three module analyses consolidated into a report, while `E2E-004` expects Scout for four library investigations consolidated into a recommendation. The two v2 disagreements occur on exactly these boundaries: run 2 chose Multi for `E2E-004`; run 3 chose Scout for `ACT-010`.
2. The executable contract does not enforce topology invariants. The prediction schema and `validate_predictions` allow `direct` with `delegate=true`; E3 proves one such invalid prediction still passes the release score because aggregate delegation accuracy remains above 95%.

The first issue weakens label validity; the second permits a structurally impossible result to pass. QG-04's aggregate metric therefore must not be interpreted as proof that every accepted prediction obeys the topology contract.

## Overclaims and release blockers

- The current CI path invokes `run_evals.py selftest`, which generates predictions from gold labels. It proves scorer mechanics, not live skill behavior. Live E2 evidence exists only in ignored `evals/results/` artifacts and is not enforced by the workflow.
- Stored `.quality/report.json` says `passed=true` but predates the current nine-check gate and omits `plugin-smoke-and-rollback`; it is ignored and is not durable CI evidence.
- [index.md](index.md) and [assessment-report.md](assessment-report.md) are deliberately historical but presently say transformation, tests, evals, CI, assets, and packaging do not exist. `validate_docs.py` checks ID/link structure, not these semantic contradictions.
- The live scorecard proves prompt routing labels only. It does not prove safe tool behavior, task quality, integration, cost, or latency.
- `dist/`, `.quality/`, and `evals/results/` are ignored. Combined with E4, neither the implementation nor its evidence can be reconstructed from the current commit.

## Verdict

**REJECT.** Local controlled use has strong instruction-level and deterministic-tooling foundations, and the routing score is promising. AAA/release acceptance remains blocked by Git/release reproducibility, invalid topology acceptance, absent single-versus-multi value evidence, absent human calibration, incomplete real-client compatibility, and non-executable end-to-end/safety claims.
