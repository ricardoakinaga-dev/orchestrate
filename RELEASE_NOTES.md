# Orchestrate 2.0.0-rc.3

Observed-client candidate. This candidate is not approved for external publication.

## Changed

- Added an exact-artifact Codex CLI harness using the officially supported `codex exec` path and repository-local `.agents/skills` discovery.
- Added explicit- and implicit-invocation probes under an ephemeral read-only sandbox with no inherited shell environment.
- Added hostile code, documentation, issue, log, and tool-output scenarios plus a synthetic secret canary and byte-identical pre/post workspace snapshots.
- Added observed JSONL-derived runtime-safety evidence and packaged-validator recovery checks instead of relying only on self-reported trace fixtures.
- Added hash-bound evidence artifacts for installation, discovery, explicit invocation, implicit routing, and recovery on the declared Codex CLI version.

## Release boundary

- A passing local client/runtime probe supports only the exact recorded Codex CLI version and environment; it does not authorize distribution.
- Commit provenance, exact-commit CI, fresh blind routing, paired operational runs, signed human calibration, product approval, and distinct final approval remain required.
- External publication, push, and production mutation remain unauthorized.

# Orchestrate 2.0.0-rc.2 (historical)

Local hardening candidate. This candidate is not approved for external publication.

## Changed

- Anchored bundled references, configuration, and helper scripts to the loaded skill directory.
- Made historical routing receipt v1 permanently non-promotable instead of refreshable through metadata edits.
- Bound operational runs to the exact source and plugin hashes and made the release gate recompute raw-run metrics.
- Added raw-trace-derived runtime-safety reports with hostile-source and action coverage.
- Added checkpoint and process-observation freshness limits to reject replayed liveness claims.
- Required tracked, hash-bound artifacts for every check of a declared supported client.
- Made JSON, YAML, frontmatter, symlink, archive, and release-provenance validation fail closed.
- Added explicit external-distribution and cross-file product-approval gates.
- Replaced repository-authored approval prose with fresh external OpenSSH signatures bound to HEAD, skill, plugin, quality bar, budgets, and role-specific principals.
- Upgraded the human labeler registry to signed identity statements with product-owner authorization and distinct Ed25519 keys.
- Made signature verification immune to `PATH` poisoning, moved external-signature preflight ahead of candidate code in the release runner, and required the final verdict to postdate product approval.
- Bound the final verdict to both the product statement and product signature, with strictly later issuance; equal timestamps fail closed.
- Added a standalone authority verifier supplied as hash-pinned protected bytes; final promotion runs it on a separate runner that executes no candidate script and re-downloads the pristine ZIP from the unprivileged build job.

## Release boundary

- Local development gates and deterministic packaging can pass; they do not grant release authority.
- Real client runtime evidence, paired operational runs, fresh blind routing provenance, human calibration, product approval, committed canonical source, exact-commit CI, and final independent approval remain required.
- External publication, installation outside the isolated harness, push, and production mutation remain unauthorized.

# Orchestrate 2.0.0-rc.1 (historical)

Release candidate for local verification. This candidate is not approved for external publication.

## Added

- Three explicit coordination topologies with authorization tracked separately.
- Deterministic validators for skill structure, budgets, routing data, action traces, task state, ownership, evidence, and recovery.
- Blind routing-evaluation protocol with development/held-out separation and repeated runs.
- Operational comparison and human-calibration harnesses.
- Deterministic plugin build, isolated installation smoke, and rollback exercise.

## Changed

- Canonical source moved from the nested `orchestrate/` directory to the repository root.
- Raw worker logs were replaced by bounded, sanitized evidence digests.
- Delegation now requires material value, specificability, verifiability, safe ownership, and authorization.

## Release boundary

- Supported evidence is limited to the local filesystem and isolated plugin harness described in `docs/compatibility.md`.
- Codex CLI, IDE, and ChatGPT desktop invocation remain unsupported until their client-smoke matrices pass.
- Automatic graders are not release authorities until blind human calibration is completed.
- External publication, marketplace installation, push, and production mutation are outside this candidate's authorization.
