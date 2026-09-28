# Target consistency at recovered-source ingestion — 2026-09-27

This implements another acceptance prerequisite under the active
[session audit](../plans/2026-09-22-session-obligation-audit.md), following
[captured target provenance](2026-09-27-target-snapshot-provenance.md).

## Contract

Target validation checks the actual captured image's length and SHA-256, then the
recorded region's bounds and digest. Addresses, offsets and sizes require exact integer
types, excluding booleans. Optional expected path/address constraints must agree.
An invocation cache captures each image once; it is not a per-row fresh-file claim.
Producer metadata is never rewritten to assert freshness.

Recovered-source parsing and seed promotion use that gate before accepting local
comparison observations. File-region bytes must also agree with the comparison's
original/destination bytes. Contradictory present source metadata must not replace
validated ledger values. Seed donor bytes remain distinct from recipient bytes.
Candidates and historical evidence remain available when required provenance is missing.

Seed compilation's raw byte-exact verdict now requires equality of the entire compiled
region. A matching prefix or relocation-normalized match is not raw equality. The
normalized match remains diagnostic. Receipts use `comparisonPolicy=raw-region-v1`;
prior comparator results cannot be reused under the stricter policy.

## Limits

File-offset consistency does not independently verify virtual-address mapping. Without
an independent expected target, the helper checks the reported target, not the intended
game/build. Results explicitly leave semantic identity and address mapping unverified.
The target observation is not yet persisted and checked by every downstream DB consumer.
Compiler/dependency closure, independent semantic binding and linked contribution remain
open. No existing production corpus was migrated or re-ingested during this increment.

## Verification and artifact

The final combined suite passed **129 tests in 0.47 seconds** against staged source
and **129 tests in 1.04 seconds** against the installed wheel. Tests use private target
images, SQLite fixtures and controlled compiler behavior. The first combined run
exposed an obsolete policy-free reuse fixture; that fixture now names the raw policy,
while an explicit negative confirms policy-free results cannot be reused. Final small
validation edits were restaged and tested before packaging.

PEP 517 wheel build and isolated install succeeded; three changed modules match
canonical source and packaged bytes. No live recovery, compiler, server activation,
or frontend rebuild is claimed. Stage: `/dev/shm/ad-target-acceptance-20260927`.

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-target-consistency/agentdecompile-2.0.1.dev0+autonomy20260927.3-py3-none-any.whl)

SHA-256: `59d79e2dc61f8aed191d1c1b2da9a9e6ffe929c55abd1f928ff3871c18a771c5`.

[Package evidence](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-target-consistency/build-evidence.json).
