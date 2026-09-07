# Verification and Integration

Read this before accepting implementation and before the final report.

## Freeze a valid quality bar

For each required result define:

| Field | Requirement |
| --- | --- |
| ID | Stable and traceable |
| Target | Binary behavior, threshold, contract, or anchored rubric |
| Evidence | Exact test, build, request, render, query, inspection, or benchmark |
| Priority | Impact and risk, independent of ease |
| Required | Whether failure blocks completion |
| Validity | Why the check exercises the real boundary and rejects a known-bad result |

Change a target only when the user or authoritative requirement changes, or evidence proves the measurement invalid. Record the revision.

## Prefer direct evidence

Use the strongest applicable source:

1. observed behavior of the real artifact;
2. deterministic test at a public boundary;
3. reproducible metric or runtime trace;
4. static analysis tied to a named rule;
5. structured manual inspection;
6. explanation or prediction, which never proves completion alone.

Keep command/procedure, environment, result, concise supporting observation, artifact reference, integrity/version, and whether the evidence predates the change. Do not inline full logs unless the relevant excerpt is itself the artifact.

Never accept a producer's `passed` flag, count, or metric as self-authenticating. For a blocking decision, require constrained raw inputs, bind them and the exact candidate by digest, reject fixtures or untracked substitutes, and recompute the decision with validator-owned logic.

## Scale judgment to risk

| Tier | Typical work | Minimum judgment |
| --- | --- | --- |
| R0 | Small, reversible, local | Lead check at changed boundary |
| R1 | Multi-file or shared behavior | Focused plus integrated checks |
| R2 | Public contract, security, migration, sensitive data | Fresh independent verifier and regression suite |
| R3 | Production, irreversible, high blast radius | Explicit authority, reversible plan, specialist gates, observation and abort criteria |

Use only applicable gates, but cover credible regression surfaces: contracts, errors, auth, persistence, concurrency, accessibility, security, performance, recovery, observability, and documentation accuracy as relevant. A build alone does not prove runtime or UI behavior; a scanner alone does not prove security.

## Separate implementation and approval

A worker reaches `IMPLEMENTED`. The Lead inspects the artifact and evidence, then moves it through review. A fresh verifier should not implement what it judges. If independent context is unavailable, strengthen executable checks and disclose the limitation; do not manufacture independence.

The verifier returns criterion-level results and `APPROVE`, `REJECT`, or `BLOCKED`, with the largest gap, evidence, severity, confidence, reproduction, and missing proof.

## Integrate deliberately

After parallel work:

1. inspect each diff and ownership boundary;
2. compare behavior with frozen contracts;
3. resolve missing wiring, duplication, naming, error, and state divergence;
4. run affected focused checks;
5. run cross-lane regression checks;
6. obtain risk-proportional independent review;
7. route fixes through targeted rework and retest.

## Verdict

Use `PASS` only when implementation and integration are complete, all required criteria have current valid evidence, applicable checks pass, and no critical/high finding remains. Use `CONDITIONAL PASS` only for explicit non-critical limitations. Use `FAIL` when a required result or usable artifact is missing. Mark unavailable checks `NOT RUN`.
