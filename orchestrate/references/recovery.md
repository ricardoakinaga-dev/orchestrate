# Failure Recovery, Safety, and Continuity

Read this reference when an agent or check fails, work spans a long session, or a task touches elevated-risk operations.

## Classify before acting

### Transient failure

Examples: timeout, temporary rate limit, interrupted process, or unavailable ephemeral service.

Retry only when the operation is safe and idempotent. Default to no more than two transient retries with an appropriate delay or reduced load. Preserve the failure output and stop sooner when the same evidence repeats.

If the retry starts immediately, keep the task `RUNNING` and record the failed attempt in its history. If it must wait for capacity or an ephemeral dependency, set `BLOCKED`, then return it to `READY` only after the retry condition is satisfied. Exhausted retries become terminal `FAILED` unless progress specifically depends on external authority or state, in which case use `BLOCKED` and name that dependency.

### Specification failure

The brief lacks a required input, has contradictory criteria, or leaves ownership ambiguous. Do not rerun the same brief. The Lead corrects the contract, updates affected dependencies, and then issues one targeted replacement task.

### Implementation failure

The artifact violates a criterion. Supply exact failing evidence and a bounded rework brief. Do not accept unrelated refactoring as a substitute. After two failed rework cycles against the same unchanged criterion, stop blind retries, reassess root cause and architecture, and escalate the blocker if no new evidence supports another attempt.

### Architecture or integration failure

The dependency graph, contract, or boundary is wrong. Pause affected downstream work, invalidate stale task states, return to planning, and revise the graph with evidence. Do not ask workers to compensate independently for a broken shared contract.

### Permission or external blocker

Credentials, production access, irreversible authorization, a user decision, or an external service is required. Continue safe in-scope diagnostics, then report the exact missing authority or state. Never fabricate success from an unavailable environment.

## Rework loop

```text
Verifier evidence
  -> Lead classifies and confirms the gap
  -> targeted rework brief
  -> implementer fixes within ownership
  -> focused retest
  -> fresh independent verification
```

Each attempt must add evidence or change a justified hypothesis. Stop an unchanged loop.

## Protect secrets and people

- Never place raw `.env` content, tokens, passwords, API keys, private keys, credentials, or unnecessary PII in agent briefs, state files, logs, or reports.
- Use variable names, redacted values, isolated fixtures, and non-production accounts.
- Treat any discovered secret as sensitive user data; do not echo it or copy it into another context.
- Keep external messages, deployments, releases, and production mutations under the user's authorization boundary.

## Protect data and source control

Workers must not automatically run destructive database resets, drops, truncation, destructive pushes, or irreversible migrations. First inspect and prepare a reversible plan; request explicit authority when the user's task does not already grant it.

Do not force-push, destructively rebase, delete branches, merge, deploy, publish, or push merely because implementation is complete. These actions require authorization in the current request. Before any authorized Git write, inspect status and diffs and include only confirmed paths.

Preserve existing user changes. Never use destructive cleanup to make tests or status look clean.

## Persist recoverable state

For long work, keep a compact checkpoint containing:

- goal, constraints, and authorization;
- frozen acceptance criteria;
- DAG, critical path, ownership, contracts, and task ledger;
- decisions and assumptions;
- exact checks run and their results;
- open gaps, blocked reason, and next action.

Reuse an existing project state mechanism. If none exists and recovery value is material, use an ignored `.orchestrate/` directory with a current `state.md`, plan, and only necessary task reports. Do not create it for simple work, commit it automatically, or store full transcripts and secrets.

Checkpoint after discovery, contract freeze, implementation, and verification when those boundaries matter. On resume, inspect the real worktree and runtime first; reconcile the checkpoint with current evidence rather than trusting stale status.

## Escalate clearly

When progress cannot continue safely, report:

- the blocked criterion and affected task IDs;
- exact evidence and attempts already made;
- what is still safe and complete;
- the smallest user decision, authority, credential, or external change needed;
- the next action once unblocked.

Never call a resource stop, missing environment, or unresolved required gate a pass.
