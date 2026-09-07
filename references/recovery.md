# Failure Recovery and Continuity

Read this after a failed check or agent, during interruption/resume, or before elevated-risk work.

## Classify first

### Transient

Timeout, temporary rate limit, interruption, or ephemeral dependency. Retry only when safe and idempotent. Use the lower of the live/user budget and the maintained default; stop sooner when evidence repeats. Preserve attempt history and partial-state checks.

### Specification

Missing input, contradictory criteria, ambiguous ownership, or invalid contract. Do not rerun the same brief. Repair the specification and affected graph, then issue one targeted replacement.

### Implementation

Artifact violates a criterion. Confirm the evidence and issue bounded rework. Do not accept unrelated refactoring. When attempts repeat without a changed hypothesis or new evidence, stop and reassess rather than looping.

### Architecture or integration

Dependency graph, contract, or boundary is wrong. Pause dependents, invalidate stale task states, revise the graph with evidence, and rerun affected checks. Do not ask individual workers to compensate for a broken shared contract.

### Permission or external state

Progress needs authority, credentials, irreversible action, user decision, or an external service. Continue safe diagnostics, then report the exact missing condition. Use `BLOCKED`, never a fabricated pass.

## Rework loop

```text
verifier evidence -> Lead confirms/classifies -> targeted rework
-> focused retest -> fresh verification
```

Every attempt must change a justified hypothesis or add evidence. Apply the configured attempt limit; exceeding it produces `FAILED` unless progress specifically depends on external state, which produces `BLOCKED`.

## Resume safely

On resume, inspect the live runtime, agents, processes, filesystem, Git status, and artifacts before trusting a checkpoint. Acquire a fresh process observation within the ledger's bounded age, then reconcile its PID and process-start token with workspace and artifact fingerprints. A replayed, future-dated, missing, or identity-mismatched observation never proves liveness. Do not restart a live or completed operation solely because a summary is stale.

Persist compact state only for work long enough to benefit. Reuse a project mechanism; otherwise store a sanitized, ignored `.orchestrate/state.json` compatible with the bundled `scripts/validate_state.py`. Resolve that validator beneath the loaded skill directory rather than the target project. Record goal, criteria, DAG, contracts, ownership, attempts, evidence references, decisions, blockers, and next action. Never store transcripts, raw secrets, or unnecessary personal data.

## Protect source and external systems

Do not use destructive cleanup to make status or tests look clean. Inspect and plan reversibility before database resets, drops, force operations, irreversible migrations, branch deletion, deploys, publication, or external messaging. Perform them only when authority exists in the current request.

Before an authorized Git write, inspect status and include only confirmed paths. Preserve unrelated changes.

## Escalate with evidence

When work cannot continue safely, report the blocked criteria/tasks, exact evidence and attempts, safe completed work, smallest missing authority or state, and the next action after unblocking.
