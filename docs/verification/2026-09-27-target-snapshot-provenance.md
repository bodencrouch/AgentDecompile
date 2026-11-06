# Captured target-image provenance — 2026-09-27

This continues the acceptance prerequisites in the [session audit](../plans/2026-09-22-session-obligation-audit.md).
It does not complete semantic identity, compiler closure or final-image acceptance.

## Corrected failure and contract

The region reader cached images by slug alone. Reusing a cache across two input
roots containing the same slug could compare against the wrong root's bytes. Cache
identity now includes the resolved image path and mapper provider. Invalid or boolean
sizes/offsets, negative addresses/offsets and out-of-range regions are rejected before
Python slicing. This prevents negative slicing from silently creating a target region.

Images remain pinned within an invocation. Repeated per-function disk reads could
mix image generations and multiply I/O. The observation records the captured whole
image SHA-256, location, length and mapper diagnostics, together with the compared
region's address, offset, size and digest. Hashes describe bytes actually supplied
to the mapper. They do not claim that the current file still has those bytes.

The compatibility byte reader remains available; the three comparison producers
carry snapshot/region metadata in their existing result and coverage observations.
Seed compile reuse must match the recorded image and region as well as source and
expected bytes; historical records without this binding require revalidation.

## Acceptance boundary

A recorded snapshot hash enables a later consumer to compare against its required
target identity; it is not independent semantic identity or current-file proof by
itself. Generic mapper names are diagnostics rather than cryptographic tool versions.
Full toolchain/dependency closure and downstream target-currentness gates remain open.
No real game recovery or live compiler/Ghidra workload was launched for this increment.

## Verification and package

The combined private-fixture suite passed **100 tests in 0.70 seconds** against staged
source and **100 tests in 0.69 seconds** against the installed wheel. Target tests use
owned byte fixtures and actual observation functions; compiler outcomes in producer
regressions are controlled. Tests cover same slug/different roots, mapper separation,
invalid region bounds, pinned snapshots versus newly captured changed files, metadata
propagation, and refusal to reuse unbound or different-image observations.

PEP 517 build and isolated target install succeeded. Three changed modules match
canonical source and wheel members. Stage: `/dev/shm/ad-target-snapshot-20260927`.
No live serving installation occurred; unchanged frontend assets were reused.

[Development wheel](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-target-snapshot/agentdecompile-2.0.1.dev0+autonomy20260927.2-py3-none-any.whl)

SHA-256: `6a5669c4fa754d8f762635560eb54194f47ce282d32771aaea70603626f3c24c`.

[Package evidence](/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-target-snapshot/build-evidence.json).
