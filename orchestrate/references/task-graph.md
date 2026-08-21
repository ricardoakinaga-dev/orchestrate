# Task Graph and Ownership

Read this reference before decomposing multi-workstream work or whenever agents could touch a shared boundary.

## Build a real DAG

Create the smallest useful set of tasks. Every node must produce an independently useful artifact or decision and have an objective check.

For each task record:

```text
ID
Title
Objective
Agent role
Dependencies
Inputs
Files/directories or mutable resources owned
Files/resources forbidden while other lanes run
Integration contract
Expected output
Acceptance criteria
Validation commands or procedures
Status
```

Dependencies must name concrete prerequisites: a decided schema, a merged interface, generated fixtures, a running service, or verified behavior. Avoid dependency edges that merely express a preferred order.

## Find the critical path

Mark nodes that control when dependent work can start. Schedule ready nodes off the critical path only when they do not consume capacity needed by higher-impact work.

Example:

```text
T00 discovery
  -> T10 contract freeze
       -> T20 backend ----\
       -> T30 frontend ----+-> T40 integration -> T50 verification
```

Do not run a child before its required contract is stable. Parallelism is useful only when it reduces elapsed time or adds independent judgment without raising conflict risk.

## Enforce ownership

Before spawning writers, construct an ownership map:

| Lane | Owns | Must not edit while parallel | Shared contract |
| --- | --- | --- | --- |
| backend | `src/api/**`, `src/services/**` | frontend and shared type files | API schema v1 |
| frontend | `src/components/**`, `src/pages/**` | backend and shared type files | API schema v1 |
| tests | assigned test paths | implementation paths unless explicitly reassigned | acceptance IDs |

Treat files as only one collision surface. Also partition schemas, migrations, databases, generated outputs, lockfiles, queues, ports, fixtures, and external resources.

Never allow simultaneous writers to the same file or mutable resource. If overlap is unavoidable:

1. extract and freeze the shared contract before parallel work;
2. assign the shared file to a single integration owner;
3. sequence the conflicting tasks; or
4. repartition work by a stable boundary.

Tests may be assigned separately only when they do not need to edit implementation-owned files. The Lead reconciles every final diff.

## Freeze integration contracts

Before connected modules run in parallel, define only the contract required for independence:

- schemas and migrations;
- request/response and error shapes;
- routes, events, and identifiers;
- shared types and interfaces;
- state ownership and lifecycle;
- compatibility expectations and feature flags.

Name the contract artifact and its owner. A contract change invalidates dependent assumptions: pause affected tasks, update briefs, and rerun their checks.

## Drive the ready queue

Use these transitions:

```text
PENDING -> READY -> RUNNING -> IMPLEMENTED -> REVIEW -> VERIFIED -> DONE
                         \-> BLOCKED
                         \-> FAILED
REVIEW -> REWORK -> RUNNING
BLOCKED -> READY
```

- `READY`: all dependencies and inputs are proven available.
- `IMPLEMENTED`: the worker returned the requested artifact and minimum required raw evidence; no acceptance implied. A completion message without either remains `RUNNING` while a focused follow-up is possible, otherwise becomes `BLOCKED` or `FAILED` according to the cause.
- `VERIFIED`: an independent or Lead-owned check confirms the assigned criteria.
- `DONE`: integration dependencies are satisfied and no required finding remains.
- For an immediately retryable transient failure, keep the task `RUNNING` and record the failed attempt separately only after checking idempotence and partial state. If retry must wait for capacity or an ephemeral dependency, use `BLOCKED -> READY`; never erase the attempt from history.
- Use terminal `FAILED` when bounded attempts are exhausted and the implementation or check remains invalid. Use `BLOCKED` when progress instead requires an external dependency, authority, credential, or user decision.

After any material contract or integration change, move affected downstream nodes back to `REVIEW` or `REWORK` rather than preserving a stale `DONE` label.
