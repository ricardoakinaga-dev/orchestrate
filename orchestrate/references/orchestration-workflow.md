# Orchestration Workflow

Read this reference for every non-trivial orchestration. It defines the Lead's lifecycle; mode-specific mechanics live in the other references.

## 1. Frame the outcome

Record:

- the user's observable outcome;
- in-scope and out-of-scope work;
- explicit constraints and repository rules;
- authorization already granted and actions that still require approval;
- the definition of done and how each required result will be proven.

Do not prescribe an architecture before discovery. Ask only when a missing choice would materially change the product, risk, or permission boundary and cannot be discovered safely.

## 2. Discover without mutation

Inspect the smallest useful set of project sources, including when present:

- `AGENTS.md`, `README.md`, `CLAUDE.md`, and relevant `docs/`;
- Discovery, PRD, SPEC, ADR, architecture, roadmap, task, and implementation-plan records;
- manifests and lockfiles such as `package.json`, `pyproject.toml`, `Cargo.toml`, or `composer.json`;
- source, tests, migrations, API contracts, Docker files, example environment files, and CI configuration;
- current branch, remotes, worktrees, `git status`, and relevant existing diffs.

Map only what affects the goal: entry points, subsystem boundaries, shared state, conventions, runnable commands, and likely regression surface. Preserve unrelated changes and never assume a clean checkout.

## 3. Reuse sources of truth and skills

For every relevant existing artifact, decide whether it is current, authoritative, incomplete, or contradicted by the code. Reuse or extend it instead of creating a parallel document by habit.

Inspect the skills exposed by the live environment. Use a specialist skill when it supplies needed domain procedures. Coordinate Discovery, PRD, SPEC, BUILD, review, security, testing, browser, or Gauntlet workflows when installed; do not reproduce their manuals inside orchestration artifacts.

## 4. Choose the execution mode

Use the delegation gate in `SKILL.md`.

- **Direct:** one small or tightly coupled change; the Lead implements and verifies it.
- **Scout-assisted:** uncertainty is separable, but implementation is small or coupled. Run read-only scouts, synthesize, then implement centrally.
- **Multi-workstream:** two or more bounded, verifiable lanes have disjoint ownership or can be sequenced through explicit dependencies.
- **Review-only:** the user asked for analysis, diagnosis, or review. Use read-only agents and checks; do not mutate the project.

Document why multi-agent execution adds value. Do not spawn agents merely to satisfy a count.

## 5. Freeze the plan and quality bar

Before implementation, define acceptance criteria with stable IDs. For each criterion include its target, priority, required/advisory status, and evidence method. A known-bad result should fail the proposed check.

For multi-workstream execution, produce a concise plan:

```markdown
# Orchestration Plan

## Objective
<observable outcome and constraints>

## Architecture understanding
<relevant boundaries and contracts>

## Tasks
| ID | Agent role | Objective | Dependencies | Ownership | Validation | Status |
| --- | --- | --- | --- | --- | --- | --- |

## Critical path
<IDs and gates>

## Acceptance criteria
<IDs, targets, and evidence>

## Integration and validation
<order and commands>
```

Use [task-graph.md](task-graph.md) to make dependencies and ownership executable rather than decorative.

## 6. Execute and monitor

Keep a ledger with `PENDING`, `READY`, `RUNNING`, `BLOCKED`, `IMPLEMENTED`, `REVIEW`, `REWORK`, `VERIFIED`, `DONE`, and `FAILED` states. Only tasks whose dependencies are satisfied may become `READY`; only verified work may become `DONE`.

At each milestone:

1. reconcile actual agent status with the ledger;
2. inspect changed files and shared contracts;
3. run targeted checks before unlocking downstream work;
4. issue a precise follow-up or rework brief when needed;
5. give the user a short status update for long-running work.

When work spans compaction or interruption, persist only the goal, frozen criteria, DAG, decisions, ownership, exact evidence, open gaps, and next action. Prefer an existing project state mechanism. Otherwise, use a small ignored `.orchestrate/` record only when its recovery value exceeds repository clutter; do not commit temporary transcripts or logs by default.

## 7. Integrate and finish

The Lead owns final integration. Reconcile all diffs, confirm shared contracts, run targeted and integrated regression checks, and obtain independent review proportional to risk. Do not let summaries substitute for artifact inspection.

Finish with:

```markdown
# Orchestration Complete

## Implemented
## Agents Used
## Files Changed
## Validation
## Independent Verification
## Remaining Risks
## Decisions / Assumptions
## Recommended Next Step
```

Use exact outcomes such as `PASS`, `FAIL`, or `NOT RUN`; never imply an unavailable check passed.
