# Target-embedded PE export identity — 2026-09-27

This is a bounded P0.4 identity-acceptance increment. It establishes one
independent target-side named witness: `target-pe-export-name-at-va-v1`.
It does not establish cross-build semantic equivalence, ABI compatibility,
linked-source contribution, current consumer target state or whole-image recovery.

## Claim boundary

A candidate is recorded as `accepted-target-pe-export` only when the exact frozen
target bytes, corpus target digest and already-admitted candidate target digest agree;
the strict PE export observation is complete; exactly one actual, case-sensitive,
non-forwarded export name matches; its `imageBase + RVA` equals the candidate VA;
and the candidate region maps to the same unambiguous file-backed bytes. Otherwise
the candidate remains useful at its address as `target-local-only` with a structured
reason. Existing logical IDs and analyzer, filename, matcher or caller labels remain
advisory and cannot make the predicate true.

The shared inventory path now hashes and parses one byte snapshot. Its strict export
observation supports PE32 and PE32+, preserves every name-table row and alias,
distinguishes actual names such as `ordinal_12` from synthesized ordinal labels, and
rejects partial, overlapping, out-of-bounds, invalid-ordinal, unterminated-string and
forwarder cases. The permissive exploratory inventory remains available separately.

Ordinary and seed ingestion share the evaluator after their existing source, target
and raw-region admission checks. The database persists status, reason and complete
evidence independently of `logical_id`. Report output labels the witness as recorded
ingestion-time evidence and explicitly says it does not recheck the target. Packaging
uses an accepted export name only when the persisted evidence is internally coherent;
otherwise it emits a deterministic address-derived name. It rechecks source bytes but
does not claim current target state.

## Candidate persistence and migration

`recovered_function` identifies concrete candidates by `(program, name, binary_id,
addr, path, source_sha256)`. This prevents a false `Foo` candidate at `Bar`'s address,
a seed candidate, or another source at the same address from replacing an unrelated
accepted candidate. Known historical `(program, name)`, interim target-key and
report-created keyless tables migrate transactionally while preserving rows, custom
columns, indexes and triggers. Historical rows gain no invented acceptance evidence.

Candidate pruning uses the same NULL-safe six-field identity. A stale sibling can be
removed without erasing another candidate. Coarser reuse proposals remain while any
candidate with their source program/name survives.

## Decisive cases and verification

The fixture target contains distinct `Foo` and `Bar` exports with identical function
bytes. For both PE32 and PE32+ the actual ingestion, database, report and package paths
demonstrate:

- `Foo` at `Foo`'s VA is accepted;
- a falsely labelled `Foo` at `Bar`'s VA remains local-only despite identical bytes;
- the independent valid `Bar` at `Bar`'s VA is accepted;
- the negative candidate cannot remove either valid candidate.

The suite also covers aliases, duplicate names, forwarders, genuine ordinal-like names,
malformed and truncated tables, snapshot and digest mismatches, wrong region offsets,
ordinary/seed equivalence, both candidate orders, multiple sources at one address,
legacy migration, candidate-specific withdrawal, report wording and deterministic
collision-safe packaging.

Independent acceptance execution passed **124 tests in 1.59 seconds against source**
and **124 tests in 2.48 seconds against the isolated installed wheel**. Four warnings
in each run are unknown `unit` markers because repository pytest configuration was
intentionally disabled in the isolated stage. A targeted storage/migration selection
also passed **9 tests with 64 deselected** in the fix worker's stage.

Independent static review initially rejected same-name candidate replacement and a
report-created legacy schema gap. After migration, full candidate identity and pruning
repairs, its scoped rereview approved the exact final revision. The reviewer did not
run tests; the acceptance owner ran the source and installed checks above.

## Package evidence

- Version: `2.0.1.dev0+autonomy20260927.8`.
- Wheel SHA-256: `23dd2a81eebadb58a5e9b1e111d7b2b5dc92308f8eb18414617a3580c9131903`.
- Build/install stage: `/dev/shm/ad-pe-identity-package-4mvq63`.
- Source/inventory/evaluator/ingress/report/package module hashes are retained in the
  external implementation and review reports and were checked equal across canonical
  source, wheel members and installed modules.
- Durable package, logs and reports are under
  `/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-target-pe-export-identity/`.

No 8080 listener was available during implementation preflight. No alternate service,
recovery job, compiler/Wine/Ghidra workload or live-game operation was launched, and
no activation claim is made. Additional target witness types, live/current consumer
checks, source contribution and fresh whole-image acceptance remain open.
