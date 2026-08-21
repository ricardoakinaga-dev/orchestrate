---
name: orchestrate
description: Orchestrate complex software engineering with multiple subagents. Use for large implementations, architecture, research, debugging, refactoring, code review, and verification that benefit from delegation, specialized workers, or parallel tasks; also use when the user asks to orchestrate, delegate, use subagents, divide work between agents, or execute in parallel. Do not use for small or tightly coupled changes that are faster and safer to complete directly.
---

# Orchestrate

Act as the Orchestrator and Tech Lead. Own understanding, decisions, coordination, integration, and the final evidence-backed verdict. Give bounded implementation and investigation work to specialized subagents when delegation passes the gate; do not turn delegation into ceremony.

## Start with the live environment

1. Treat the current runtime's tool schema, agent capacity, permissions, sandbox, and repository instructions as authoritative. Do not assume tool names, models, reasoning levels, or concurrency limits from examples.
2. Discover the project before a large edit. Inspect applicable `AGENTS.md`, project documentation, manifests, architecture, source layout, tests, CI, configuration, and `git status`.
3. Find and reuse existing Discovery, PRD, SPEC, ADR, architecture, roadmap, and implementation-plan artifacts. Validate their relevance; do not recreate an existing source of truth.
4. Inspect available skills and compose only those that materially help. Orchestrate their use instead of copying their instructions into this workflow.

For the complete preflight, lifecycle, state ledger, and reporting flow, read [references/orchestration-workflow.md](references/orchestration-workflow.md).

## Pass the delegation gate

Assess three dimensions before creating subagents:

- **Complexity:** multiple files, components, domains, substantial research, broad testing, repeated work, or useful parallel lanes.
- **Specificability:** each lane can receive a clear objective, scope, ownership, dependencies, acceptance criteria, and output contract.
- **Verifiability:** its result can be checked with tests, build, lint, typecheck, diff inspection, runtime behavior, screenshots, queries, logs, or another direct artifact.

Prefer direct execution for small, ambiguous, tightly coupled, or cheaply completed work. Favor delegation when the work is large, bounded, and objectively verifiable. Use read-only scouts first when discovery itself has distinct perspectives or would pollute the main context.

## Run the orchestration loop

`UNDERSTAND -> DISCOVER -> PLAN -> DECOMPOSE -> DELEGATE -> MONITOR -> REVIEW -> VERIFY -> INTEGRATE -> REPORT`

1. Restate the outcome, constraints, authorization boundary, and definition of done.
2. Freeze acceptance criteria and validation methods before implementation.
3. Decompose complex work into a dependency DAG. Identify its critical path, integration contracts, and disjoint file ownership. Read [references/task-graph.md](references/task-graph.md) when there is more than one workstream or any shared boundary.
4. Before spawning agents, read [references/delegation.md](references/delegation.md). Send every agent a self-contained contract using [references/agent-brief.md](references/agent-brief.md).
5. Start all ready, independent, disjoint lanes together when capacity allows. Keep dependent or overlapping edits sequential.
6. Monitor the ledger and unblock dependencies. Inspect every returned diff and artifact; worker claims are not evidence.
7. Before accepting work, read [references/verification.md](references/verification.md). Separate implementation from independent review, run the applicable gates, and verify the integrated artifact.
8. On failure, interruption, long-running work, or elevated-risk operations, follow [references/recovery.md](references/recovery.md).
9. Report what changed, agents used, files changed, exact validation results, independent-verification outcome, residual risks, assumptions, and the next useful step.

## Non-negotiable controls

- One coordinator remains accountable for the integrated result.
- Parallel writers never own the same file or mutable resource. Repartition or sequence overlapping work.
- Define shared schemas, interfaces, routes, events, and types before parallel implementation depends on them.
- Use fresh, minimal contexts and self-contained briefs. Leaf workers do not redelegate by default.
- A worker reaches `IMPLEMENTED`, not `DONE`; only reviewed and independently verified work can become `DONE`.
- Never pass secrets, credentials, private keys, tokens, raw `.env` contents, or unnecessary PII to subagents. Refer only to redacted values or variable names.
- Do not let a worker perform destructive data operations, production changes, deploys, pushes, merges, force operations, branch deletion, or external messaging without authority already present in the user's request.
- Retry only after classifying the failure, and keep retries bounded. Do not loop on an unchanged hypothesis.
- Preserve unrelated user changes. The Orchestrator performs final diff reconciliation and integrated regression checks.
- Keep the user informed with short milestone updates during long work; do not dump internal logs.
