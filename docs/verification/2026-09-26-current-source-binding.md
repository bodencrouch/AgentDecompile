# Current-source comparison binding — 2026-09-26

This implements a producer/consumer portion of P0.4 in the
[session audit](../plans/2026-09-22-session-obligation-audit.md). The full goal and
semantic identity, contribution, target/toolchain and dependency acceptance remain open.

## Changed behavior

Legacy compilation captures exact source bytes before compiling its private payload,
and writes source and compared-region SHA-256 values into existing coverage JSONL.
Named recovery compiles private source snapshots and recompiles the exact final emitted
source before binding the published observation. Prefix-only and relocation-masked
matches do not earn raw byte-exact status. Nonzero compiler exits are failures even
when an object was written. Seed audit captures a source snapshot, checks its bytes
again afterward, rejects changed inputs, and refuses reuse of old unbound receipts.

The shared `coverage_evidence` predicate checks current source bytes against that
producer digest. It does not create semantic or contribution acceptance. Ordinary
recovered-source ingestion and seed promotion require this binding. Later negative
coverage rows withdraw earlier positives. Rejected source files and historical
observations remain available; ingestion can report source-binding rejections.
The existing shrink guard remains in force rather than silently rebuilding a large
corpus with fewer rows. No existing corpus was migrated or rewritten by this work.

Collection writes exact bound producer bytes into the verified directory without
injecting a metadata header. Missing/stale bindings produce explicitly unverified
candidates. Stale prior output is preserved under a unique unverified path and reported.
Size/convention can be taken from ledger metadata when the verified source has no header.
Legacy textual verifier output and DB restoration cannot gain new source provenance
merely by hashing whatever file exists now; use the existing current-source revalidator.

## Evidence and limits

Final eight-file regression suite: **51 passed in 0.45 seconds** against staged source
and **51 passed in 0.49 seconds** against the installed wheel. The wheel build and
isolated installation succeeded; six changed module byte sequences match canonical
source and packaged members. Stage: `/dev/shm/agentdecompile-source-binding-20260926`.
An initial staging build lacked copied packaging scripts and failed; after restoring
those required inputs, the build completed. No release or serving activation occurred.

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-26-source-binding/agentdecompile-2.0.1.dev0+autonomy20260926-py3-none-any.whl)

SHA-256: `5af7f3f20922b8cb7c9b8e2e344d7b8fb5ba375a6a9bf1544f4d676f6e59fefa`.

[Source/package evidence](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-26-source-binding/build-evidence.json).

Compiler behavior in the focused regression cases is controlled/mocked. These tests
exercise source substitution, concurrent source changes, false verdicts, exact-byte
preservation, prefix/masked rejection and compiler failure with a leftover object.
They are not fresh game recovery, full-image comparison or a live compiler qualification.

The database still stores mutable source paths without a persistent currentness state.
Checking at ingestion does not make later reads permanently current. Full independent
semantic binding, source-contribution selection and downstream invalidation remain open.
The older authoritative-packaging module also has pre-existing calling-contract issues;
this increment does not claim that its full product path runs successfully.

No 8080 listener was present at preflight; no service, live recovery or game was launched.
