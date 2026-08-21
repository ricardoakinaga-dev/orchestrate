# Agent Briefs and Returns

Read this reference before delegating or issuing rework. Replace every placeholder and omit irrelevant sections; never send the instructional comments.

## Worker brief

```markdown
ROLE
You are the <specialist> for task <ID>. Execute this task yourself; do not redelegate.

OBJECTIVE
<one observable local outcome>

PROJECT CONTEXT
<minimum architecture and product facts needed>

AUTHORITATIVE INPUTS
<exact files, documents, contracts, and prior task artifacts>

TASK
<bounded implementation or investigation>

SCOPE
<included behavior>

OUT OF SCOPE
<adjacent behavior and decisions reserved for the Lead>

OWNERSHIP
You may edit: <exact files/directories/resources, or read-only>.
You must not edit: <other active lanes and shared resources>.
Preserve unrelated user changes.

DEPENDENCIES AND CONTRACTS
<satisfied prerequisites and frozen interfaces>

EXISTING CONVENTIONS
<applicable repository rules and nearby patterns>

IMPLEMENTATION REQUIREMENTS
<non-obvious constraints only>

ACCEPTANCE CRITERIA
<stable IDs and targets>

VALIDATION
<exact safe commands or procedures and expected artifacts>

SAFETY / AUTHORIZATION
<secrets, data, production, external-write, and approval boundaries>

EXPECTED RETURN
Use the structured result below. The minimum evidence required for this task is: <named commands/procedures and artifacts>. Return that raw evidence; do not approve your own work.
```

## Worker result

```markdown
TASK: <ID>
STATUS: IMPLEMENTED | BLOCKED | FAILED

SUMMARY
<observable result>

FILES / RESOURCES CHANGED
<exact paths and purpose>

IMPLEMENTATION
<concise behavior and contract changes>

ROOT-CAUSE OR DECISION EVIDENCE
<observations that distinguish cause from symptom>

VALIDATION
- `<exact command or procedure>` -> <exit/result>

ARTIFACTS
<logs, screenshots, reports, metrics, URLs, or none>

RISKS AND ASSUMPTIONS
<remaining uncertainty>

KNOWN ISSUES
<failures or missing evidence; never hide them>

RECOMMENDED NEXT STEP
<integration or rework suggestion, not a PASS verdict>
```

## Read-only scout brief

Use the worker brief, but explicitly set ownership to read-only and ask for:

- exact files, symbols, commands, and observed behavior;
- subsystem and dependency map limited to the question;
- risks ranked by impact and confidence;
- candidate task boundaries and likely collisions;
- missing evidence.

Do not reveal the Lead's favored solution when independent investigation is the goal.

## Independent verifier brief

```markdown
You are the independent Verifier. Do not edit files.

GOAL
<global or local observable outcome>

ACCEPTANCE CRITERIA
<stable IDs and targets>

APPLICABLE RULES
<repository and safety rules>

ARTIFACT TO INSPECT
<diff, files, running URL, screenshots, endpoints, data, or build artifact>

REPRODUCTION / VALIDATION
<safe commands and environment facts>

Inspect the artifact directly. Do not trust worker claims or infer missing runs. Return APPROVE, REJECT, or BLOCKED; list the largest gap first with evidence, severity, confidence, affected criteria, and reproduction steps. Do not fix the work.
```

Give a verifier the result artifact and criteria, but omit the implementer's rationale, expected conclusion, suspected fix, and prior verdict when they are not necessary. This reduces confirmation bias.

## Targeted rework brief

Do not say only "try again." Include:

- the failed criterion and direct evidence;
- exact reproduction;
- why the prior evidence was insufficient;
- unchanged ownership and safety boundaries;
- the required new evidence.

Treat a verifier's proposed cause as a hypothesis until the implementer or Lead confirms it.
A focused follow-up for a missing artifact or required evidence counts as an attempt. After two deficient returns with no new evidence, classify the task `FAILED` or `BLOCKED` under [recovery.md](recovery.md) instead of continuing an evidence-only loop.

## Integration reviewer brief

Ask a fresh read-only reviewer to inspect the complete artifact for interface conflicts, incomplete wiring, duplicated rules, divergent state or error behavior, ownership violations, and regressions across workstreams. Give it the original criteria and integrated commands, not the builders' conclusions.
