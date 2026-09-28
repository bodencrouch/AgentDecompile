# Recovered-source freshness at consumption — 2026-09-26

This extends [producer/source binding](2026-09-26-current-source-binding.md).
The full [session goal](../plans/2026-09-22-session-obligation-audit.md) stays active.

## Implemented contract

`recovered_function` gains nullable `source_sha256` through additive schema migration.
Both insertion paths persist the digest already checked against the producer's observation.
No migration hashes current files to manufacture past provenance; old rows stay null.

The shared file reader checks current bytes without modifying the source or database.
Covered consumers now require that match before treating database presence as a reason
to suppress outstanding work: leftover filtering, genproject automatic recovered skips,
bulk Ghidra real-C logical IDs, and named-recovery address exclusions. Genproject's
optional coverage ledger also requires an explicit source path and matching digest;
a later negative row withdraws that ledger's earlier positive. Explicit user-supplied
skip manifests remain intentional exclusions, not scientific acceptance evidence.

The database-backed readable-source packager reads source once, checks its recorded
digest, and writes those exact bytes. Missing/stale/unreadable source produces a
reported exclusion. Existing destination files are preserved through exclusive creation.

Restoration never reconstructs byte-exact success from DB membership. New restoration
ledger rows are explicitly reused and unverified, even when their original source digest
matches. Exact source bytes are preserved, matching digests may disambiguate same-name
package files, and existing source files are never overwritten. Legacy schemas are
read without migration by these readers; the explicit ingestion schema initializer
owns the additive migration. Dry-run restoration does not mutate the database.

## Scope and outstanding acceptance

These predicates observe source bytes at a point in time. They do not establish
independent semantic identity, recipient equivalence, compiler/dependency freshness,
linked contribution or final whole-image equality. Historical advisory archive witnesses
remain available with their existing caveats. This is an inventory of the covered
consumers, not a claim every SQL reader now implements full acceptance. In particular,
progress-summary labels and semantic sibling shortcuts require their own remaining work.

Only isolated private fixtures were migrated, restored or packaged for tests. No live
corpus mutation, Ghidra analysis, compiler/recovery operation or server startup occurred.
No 8080 listener was present at preflight. Final validation and packaging completed on 2026-09-27.

## Final verification and artifact

The combined regression suite passed **84 tests in 0.64 seconds** against staged source,
and **84 tests in 0.50 seconds** against the installed wheel. Selector tests import the
actual modules. Checks include old-schema migration without fabricated hashes,
post-ingestion source edits/deletion, unaffected observations, malformed identifiers,
restoration exact bytes/dry-run, same-name package selection, and package check/copy
races. Compiler behavior inherited from the prior regression suite remains controlled;
no game compiler or live recovery was run.

PEP 517 wheel build and isolated target install succeeded using system Python. Eight
changed modules match canonical source and wheel bytes. Tests used explicit source or
installed `PYTHONPATH`, disabled external pytest plugins, `--noconftest -c /dev/null`,
and private `/dev/shm` fixtures. The package preserves prior working-tree context;
it is not a clean release or a serving activation. Frontend assets are reused unchanged.

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-source-freshness/agentdecompile-2.0.1.dev0+autonomy20260927-py3-none-any.whl)

SHA-256: `a434a9449303a60cfa1d5a0bb1287742e27f01cc79535c6861e3218a756ff3f3`.

[Source/package hash manifest](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-source-freshness/build-evidence.json).
