# Task Graph and Ownership

Read this before decomposing multiple workstreams or sharing a mutable boundary.

## Define executable nodes

Create the smallest DAG whose nodes produce independently useful artifacts or decisions. Record for each task:

```text
ID, title, objective, role, dependencies, inputs
owned and forbidden files/resources
shared contract name/version
acceptance criteria and validation
expected artifact and evidence digest
risk tier, budget, status, attempt history
```

Dependencies must name proven prerequisites such as a decided schema, verified interface, fixture, or running service—not a preferred order.

## Find the critical path

Start a node only when its dependencies are satisfied and contracts current. Schedule optional work only when it does not displace higher-value critical or verification work.

```text
discovery -> contract
              |-> lane A --|
              |-> lane B --|-> integration -> verification
```

## Enforce ownership

Partition both files and non-file resources: schemas, migrations, generated output, lockfiles, databases, fixtures, queues, ports, and external systems. Parallel writers never share a mutable resource.

When overlap is unavoidable, use one of these strategies before execution:

1. freeze the shared contract and assign its file to one owner;
2. sequence the conflicting tasks;
3. repartition on a stable boundary;
4. use an isolated worktree or fixture when it materially reduces risk.

The Lead reconciles every final diff and preserves unrelated user changes.

## Freeze contracts

Define only what independent lanes need: schemas, request/response and error shapes, routes, events, shared types, state ownership, lifecycle, compatibility, and flags. Name the artifact and version. A material contract change invalidates dependent assumptions and returns affected tasks to `REVIEW` or `REWORK`.

## Use explicit states

```text
PENDING -> READY -> RUNNING -> IMPLEMENTED -> REVIEW -> VERIFIED -> DONE
                         |          ^            |
                         |          |            -> REWORK -> RUNNING
                         |          -> BLOCKED
                         -> FAILED
BLOCKED -> READY
```

- `READY`: inputs and dependencies are proven available.
- `IMPLEMENTED`: artifact and evidence digest returned; no approval implied.
- `VERIFIED`: current evidence confirms assigned criteria.
- `DONE`: integration dependencies are satisfied and no required finding remains.
- `BLOCKED`: progress requires external state, authority, credential, or decision.
- `FAILED`: bounded attempts are exhausted and the result remains invalid.

An immediately retryable, idempotent transient error keeps the task `RUNNING` with attempt history. Every attempt has a stable `hypothesis_id` and records SHA-256 references that resolve through the ledger's local evidence registry; a retry of that hypothesis must add a new registered digest. Never erase failures or preserve stale `DONE` after contract changes.

## Validate machine-readable ledgers

When this skill's bundled tooling is available, resolve `scripts/validate_state.py` beneath the loaded `orchestrate` skill directory and invoke that absolute path on the ledger. Never substitute a same-named target-project script.

Ledger schema v3 binds active work to observed process identity, checkpoint generation, a bounded checkpoint age, and workspace/artifact fingerprints. It binds current terminal evidence to a local artifact, a local evidence manifest, and their SHA-256 digests. The manifest repeats the exact check/result and canonical task-contract snapshot. The validator checks IDs, dependencies, cycles, status/dependency consistency, normalized and symlink-resolved active ownership collisions, contract freshness, registered retry evidence, required evidence, attempt limits, and stale or future-dated `RUNNING` observations when invoked through its CLI. Its result complements live process inspection; it does not decide architecture or user intent.
