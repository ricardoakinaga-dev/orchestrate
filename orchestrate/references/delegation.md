# Delegation and Parallel Execution

Read this reference immediately before creating subagents.

## Discover the live controls

Inspect the current agent-tool schema and capacity first. Use the controls actually exposed for spawning, listing, steering, interrupting, following up, and waiting. Tool names and arguments can evolve; examples in documentation are not authority over the live runtime.

Respect the current permission and sandbox model. Subagents commonly inherit parent constraints, but verify rather than assume. Do not request broader permissions, a different model, or a reasoning override unless the task and runtime justify it.

Prefer inherited model and reasoning defaults. When live controls permit explicit selection, choose by task difficulty and cost rather than fixed names:

- fast/low or medium reasoning for bounded read-only scans and repetitive extraction;
- medium/high for implementation with meaningful edge cases;
- high or stronger for architecture, security, adversarial review, or ambiguous debugging.

Never hardcode a model that may disappear. If only one option exists, use it.

## Choose the smallest useful team

Select roles from the actual DAG. Typical roles include scout, architect, product, backend, frontend, database, security, test, QA, debugger, performance, documentation, reviewer, integration, and verifier. These are examples, not a mandatory roster.

Use read-only scouts when separate investigation can reduce uncertainty about architecture, dependencies, security, or test coverage. For large plans, a fresh read-only plan reviewer can challenge missing dependencies, collisions, assumptions, tests, and acceptance criteria before writers start.

Do not create agents for work the Lead can finish more cheaply and safely. Do not create idle specialists, duplicate investigations without an independence purpose, or a swarm without a graph.

## Spawn with minimal context

Prefer a fresh context plus a self-contained brief and exact relevant paths. If the live spawn control offers history inheritance, select the smallest history window that supplies indispensable context; do not forward the entire conversation by default.

Every agent receives:

- one role and one bounded objective;
- relevant project facts and authoritative documents;
- explicit in-scope and out-of-scope work;
- owned and forbidden files/resources;
- dependencies and stable integration contracts;
- acceptance criteria and exact validation procedures;
- safety and authorization limits;
- a structured return contract.

Use [agent-brief.md](agent-brief.md). Leaf workers execute their own task and must not spawn more agents unless the Lead explicitly authorizes a justified hierarchy supported by the runtime.

## Parallelize safely

Before starting parallel writers, verify:

1. ownership is disjoint, including generated and shared resources;
2. integration contracts are stable;
3. dependencies are satisfied;
4. each task has an isolated check;
5. available capacity leaves room for monitoring or urgent verification when needed.

Start all ready independent lanes without serial waiting. Then wait efficiently for mailbox or status changes; do not busy-poll. Continue useful Lead work such as preparing integration checks while agents run, but do not edit files owned by active workers.

When ownership overlaps, sequence the work or assign one integration owner. Never ask two parallel workers to edit the same file and hope Git reconciliation will solve it.

## Worktrees and isolation

Consider a Git worktree or disposable fixture only when it materially protects a dirty checkout, isolates risky work, or allows independent builds. Before creating one, inspect repository status, branches, submodules, nested repositories, and existing worktrees.

Keep worktree ownership explicit. Do not create worktrees indiscriminately, delete user branches, or discard existing changes. Integrating a worktree remains the Lead's responsibility.

## Monitor and steer

Maintain the task ledger from [task-graph.md](task-graph.md). Use status controls to detect completion or blockage, and send focused follow-ups when an agent is drifting. Interrupt only when continuing would waste resources, collide with ownership, or violate safety.

An agent completion message can advance a task to `IMPLEMENTED` only when the requested artifact and minimum required raw evidence named in its brief are present. Otherwise keep it `RUNNING` for a focused follow-up or classify it `BLOCKED`/`FAILED`. Count deficient follow-ups toward the bounded attempt policy; never loop only to request the same missing evidence. Inspect the actual filesystem, diff, and raw checks before moving it further. Close or leave completed threads according to the live runtime; do not rely on a closed thread as evidence of integration.
