# Verification and Integration

Read this reference before accepting any delegated implementation and before the final report.

## Freeze an evidence-backed quality bar

For every required result define:

| Field | Meaning |
| --- | --- |
| ID | Stable criterion identifier |
| Target | Binary behavior, contract, threshold, or anchored qualitative result |
| Evidence | Exact test, build, request, render, inspection, query, or benchmark |
| Priority | Impact and risk, independent of ease |
| Required | Whether failure blocks completion |
| Validity | Why the check exercises the real boundary and would reject a known-bad result |

Change the bar only when the user changes the goal, an authoritative requirement changes, or evidence proves the measurement invalid. Record the revision; never lower a target because the implementation misses it.

## Prefer direct evidence

Use this order:

1. observed behavior of the real artifact;
2. deterministic automated test at the public boundary;
3. reproducible metric or runtime trace;
4. static analysis tied to a named rule;
5. structured manual inspection;
6. explanation or prediction, which never proves completion alone.

For each check retain the exact command/procedure, environment, exit/result, relevant raw output summary, artifact path, and whether it predates the change. Run the check yourself or through a verifier; a worker's statement that it passed is not evidence.

## Verify by change type

Use only applicable gates, but cover the credible regression surface.

- **General code:** focused tests, relevant suite, lint, typecheck, build, diff inspection, errors, and changed public contracts.
- **Frontend/UI:** start the real app; exercise pointer, keyboard, loading, empty, error, and recovery states; inspect responsive widths, accessibility, console/network output, and screenshots. A build alone does not prove UI quality.
- **Backend/API:** request/response schemas, status and error semantics, validation, authentication, authorization, persistence, migrations, concurrency, idempotency, logs, and integration tests.
- **Database:** constraints, migration application on isolated representative data, rollback or roll-forward plan when required, transactions, query behavior, and data invariants. Never run destructive validation against real data.
- **Security:** actor/resource/action authorization, input boundaries, secret exposure, dependencies, session behavior, rate/replay controls, and auditability. A single scanner cannot prove security.
- **Performance/reliability:** representative workload, tails, cold/warm behavior, failure injection in isolation, startup/shutdown, retries, recovery, resource bounds, and observability.
- **Documentation/review-only:** accuracy against authoritative sources, links, examples, scope, and direct code or artifact evidence; do not mutate in review-only mode.

## Separate implementation and judgment

Move a worker result only to `IMPLEMENTED`. The Lead inspects its diff and targeted evidence. Whenever justified, use a fresh read-only verifier that did not implement the change.

The verifier reports criterion-by-criterion results plus the largest remaining gap, evidence, severity, confidence, reproduction, and missing evidence. It returns `APPROVE`, `REJECT`, or `BLOCKED` and does not edit.

If independent context is unavailable, strengthen executable gates and disclose the limitation. Do not manufacture independence by relabeling the implementer's own test run.

## Integrate deliberately

After parallel work:

1. inspect every diff and confirm file ownership was respected;
2. compare implementation against the frozen contracts;
3. resolve missing wiring, duplication, divergent naming, errors, and state behavior;
4. run each affected focused check;
5. run integrated regression checks across workstream boundaries;
6. obtain a fresh integration review for material multi-workstream changes;
7. route any fix through targeted rework and retest.

Do not let passing unit tests substitute for an end-to-end criterion that crosses real boundaries.

## Definition of done

The global task is `DONE` only when:

- implementation and integration are complete;
- every required acceptance criterion has current evidence;
- applicable tests, build, lint, typecheck, and runtime checks pass;
- critical and high findings are resolved or explicitly block completion;
- independent verification has approved the relevant risk surface, or its absence is disclosed without claiming an unconditional pass;
- unrelated user changes remain preserved;
- residual risks and unavailable checks are reported honestly.

Use `PASS` only for proven completion, `CONDITIONAL PASS` for a non-critical limitation or missing independent environment, and `FAIL` when a required criterion or usable artifact is missing.
