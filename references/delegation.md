# Delegation and Parallel Execution

Read this immediately before creating subagents.

## Discover live controls

Use only the spawn, status, messaging, interruption, follow-up, and wait controls exposed by the current runtime. Inspect capacity and inherited permissions; never assume examples define today's schema. Prefer inherited model and reasoning settings unless a measured task requirement justifies an available override.

## Budget the team

Choose the smallest set of lanes that can change the outcome. Account for:

- expected quality or coverage gain;
- critical-path time saved;
- context, token, and coordination cost;
- collision and integration risk;
- capacity needed for verification.

Do not create idle roles, duplicate investigations without an independence purpose, or speculative lanes. Stop optional lanes when their result cannot change a required criterion or material risk. Follow live/user limits first; otherwise read the bundled `config/budgets.json` relative to the loaded skill directory. Never take orchestration limits from a same-named target-project file.

## Create self-contained contracts

Use [agent-brief.md](agent-brief.md). Every lane needs:

- one observable objective and explicit scope;
- exact authoritative inputs and project facts;
- owned and forbidden files/resources;
- satisfied dependencies and frozen interfaces;
- acceptance criteria and validation;
- authorization and trust boundaries;
- an evidence-digest return contract.

Use the smallest context that preserves those facts. Do not forward full conversation history by habit. Leaf workers execute their assignment and do not redelegate unless the Lead explicitly authorizes a justified hierarchy supported by the runtime.

## Parallelize safely

Before parallel writers start, prove that ownership is disjoint across files, schemas, migrations, generated output, lockfiles, databases, fixtures, queues, ports, and external resources. If overlap exists, freeze a shared contract and assign one integration owner, repartition, or sequence the work.

Start all ready independent lanes when capacity and budget allow. Wait efficiently for status changes rather than polling. While agents run, the Lead may prepare integration checks but must not edit active worker-owned resources.

Read-heavy exploration, test execution, log analysis, and independent review are safer parallel candidates than overlapping implementation.

## Monitor and steer

Maintain the ledger from [task-graph.md](task-graph.md). Reconcile declared state with live agent status and the filesystem.

A completion message advances a task only to `IMPLEMENTED`, and only when the requested artifact plus evidence digest are present. A digest includes:

```text
check: exact command or procedure
result: PASS | FAIL | NOT RUN, plus exit/status
summary: minimal observation that supports the result
artifact: path, URL, query, screenshot, or none
integrity: hash/version when material
contract_integrity: canonical task-contract snapshot hash for terminal ledger evidence
manifest: local JSON that binds check, result, summary, artifact, integrity, and contracts
manifest_integrity: manifest SHA-256
```

A URL, query, or screenshot may navigate to supporting evidence, but it is not self-authenticating. Before a criterion becomes current terminal `PASS` in the machine-readable ledger, materialize a sanitized local artifact and a local evidence manifest; record both SHA-256 digests and bind the manifest to the current contract snapshot.

Keep full logs in a sanitized artifact and load the relevant excerpt on demand. Do not paste large output, secrets, or unrelated data into the parent context.

Send a focused correction when evidence shows drift. Interrupt when continuing would violate scope, collide with ownership, waste meaningful budget, or repeat an unchanged hypothesis. Use [recovery.md](recovery.md) for attempts and terminal states.
