# Raw local observations and reconciliation — 2026-09-27

This is a partial acceptance-correctness increment under P0.4 in the
[session audit](../plans/2026-09-22-session-obligation-audit.md). Independent review
approved the corrected revision recorded below. The scoped development package is
built and verified; full P0.4 acceptance remains open.

The inspected producer trusted an embedded `original machine code` header even
when it disagreed with the required raw image. Its masked comparator also accepted
a matching prefix of a longer compiled section. The reconciliation consumer treated
truthy `ok` as byte-exact recovered C, even though `ok` meant relocation-masked
equality, and wrote `exactPlacementHashEqual: true` without computing placement.

The producer now requires the embedded bytes, declared address, and available
header/database sizes to agree with the mapped raw region. Strict UTF-8 source
bytes are frozen for compilation. Receipts distinguish complete raw equality
(`rawEqual`) from relocation-masked diagnostics (`ok`/`maskedEqual`) and carry
source path/digest, whole-target snapshot, region address/offset/size/digest,
and comparison policy. A matching prefix no longer qualifies. Main records source
and target identity for negative observations too, permitting withdrawal.

The reconciliation report requires a specific target and validates source freshness,
readable C, raw equality, target snapshot/region, actual file-backed PE address mapping
and expected function size. Overlapping or unbacked regions cannot qualify. Receipt
order controls supersession; a later negative withdraws an earlier observation for
the same source/address. Malformed inputs produce rejection diagnostics.

`rawLocalObservedC` is the explicit count. `byteExactRecoveredC` remains its compatibility
alias; it does not certify semantic identity, current toolchain, linked contribution
or a full rebuilt image. Those unverified scopes are explicit in the report.
`exactPlacementHashEqual` is null because this consumer performs no placement comparison.

## Verification scope

The final combined suite passed **67 tests in 0.84 seconds against source** and
**67 tests in 0.73 seconds against the isolated installed wheel**. This includes
masked-only output exclusion, owner conflicts, tampered artifacts, no-clobber
publication, missing/corrupt cache ownership recovery, initial dependency failure,
partial section overlaps and dependency restoration followed by fresh publication
and cache reuse. Source fixtures control compilation and object extraction.

The initial implementation passed **57 tests in 1.92 seconds against source** and
**57 tests in 0.49 seconds against the installed development wheel**. These are
historical results for the pre-review implementation, not validation of the current
revision. That suite covers
embedded target disagreement, missing/invalid addresses and sizes, malformed hex,
strict source encoding, invalid relocation offsets, whole-length comparison,
source/target staleness, PE mapping, expected sizes, negative supersession,
malformed independent inputs, cache invalidation and periodic audit behavior.

Two integration cases exercise the real verifier entry point through persisted
receipts, corpus function rows and the actual reconciliation entry point: raw equality
counts one observation; relocation-only equality counts zero. Compiler execution and
object-section extraction are controlled fixtures. These are not live compiler,
whole-image or game runtime demonstrations.

Build and isolated installation succeeded in `/dev/shm/ad-raw-observations-20260927`.
8080 had no listener at source preflight; no service or recovery workload was launched.
No package activation in a serving process is claimed. Independent symbol identity,
linked-source contribution, transitive toolchain discovery and general acceptance
remain open, as does the full session goal.

Dashboard variant/permuter totals use a separate aggregation route and have not been
qualified by this increment. No claim that every UI coverage counter now uses these
raw-observation gates is made.

## Review and current validation state

Independent review rejected the initial implementation: masked-only comparisons
could publish target-patched substitution artifacts, negative observations left
previous artifacts active, a negative candidate could suppress another source at
the same address, and producer/consumer PE mapping rules differed.

The first correction introduces owned artifact publication and withdrawal, keeps
masked-only results diagnostic, reconciles by source/address, and shares a strict
file-backed region resolver. Its focused 25-test result does not replace the
combined regression check or independent re-review.

An intermediate combined source recheck stopped at **1 failed, 49 passed in 0.80 seconds**:
`test_verification_cache_basis.py::test_emitted_artifact_change_forces_reverification`.
The old fixture emitted a binary without an ownership record. It now models a real
owned artifact and requires changed bytes to remain preserved with an explicit
`artifact-publication-blocked` result. The exact intermediate output is retained at
`/home/brunner56/Documents/raw-observation-fix1-combined-recheck.log`.

Scoped re-review also identified remaining correction requirements: losing a
complete verification basis must withdraw an owned substitution artifact, and
ownership recovery must work after a crash between manifest publication and cache
checkpoint persistence. A missing cache entry cannot erase the manifest's withdrawal
responsibility. PE mapping must reject an overlapping section even when the second
section intersects only part of the requested region. These findings and a subsequent
restore-after-withdrawal regression were corrected and approved in the final rereview.

## Final package and review evidence

- Version: `2.0.1.dev0+autonomy20260927.7`.
- Wheel SHA-256: `58781bd7b4fc20d6e5c51bebf38f711c5ec61030bf810ef9fbe0a923dc8522c8`.
- Producer SHA-256: `a009df950400e92d8347bcb1354b9c65d06f0d2a51562736554b4c390d3c8c9e`.
- Consumer SHA-256: `cff3abb6739553356091baff961e4a1e02fee771ab34aa45f6824eda0538ccf1`.
- Build/install staging: `/dev/shm/ad-raw-observation-fix1-3Ktp62`.
- Durable wheel, source/installed logs, build/install logs and revision-aware review:
  `/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-raw-local-observations/`.

The acceptance owner checked imported module locations and byte equality of both
reviewed modules across canonical source, staging, wheel members and installed
modules. The final reviewer inspected source and regressions without rerunning tests;
the source/installed executions above were performed separately by the acceptance owner.

Artifact locks coordinate cooperating producers. They do not guarantee immunity to
a noncooperating writer replacing a file between withdrawal checks and rename.
Filename-only relink consumers can still read preserved disputed or legacy artifacts;
their receipt-aware admission remains a separate required integration. This package
does not claim complete downstream withdrawal, semantic identity, linked contribution,
real compiler equivalence, service activation or whole-image acceptance.
