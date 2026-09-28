# D3 destination isolation and algorithm-basis revision

Date: 2026-09-27. Version: `2.0.1.dev0+autonomy20260927.16`.
Status: focused source and installed verification passed; independent final
artifact review approved the bounded change with no scoped blocker.

## Behavior changed

`propagate.bind_identities` previously demoted conflict rows using the run, source
binary/address and destination address, but omitted the destination binary. A
loser in one destination build could therefore demote an independent winner in a
different build at the same numeric address. The UPDATE now includes the destination
binary. Candidate order, confidence and winner-selection policy remain unchanged.

The cascade basis is now
`phase0.4+key:content_sha256+dep:content_sha256_16`. The exact phase0.3 revision is
retained in history so the existing resolver can reconstruct the prior basis.
The actual export entry refuses stale stamped state. This does not imply every
direct mutator is basis-gated, nor does it repair historical demoted rows or execute
a rebaseline against the user's corpus.

This is a bounded repair within the original portable-plan D3, with shared
determinism-basis implications. It does not close all weekend determinism or
recovery requirements.

## Verification

The source-overlay runs are retained separately: 20 propagation cases in 1.45
seconds, five basis/history/export-refusal cases in 0.35 seconds, and seven cascade
cases in 1.00 second. The destination regression exercises eight combinations of
insertion order, seed order and destination content-hash ordering. The existing
committed cascade fixture checks shuffled layouts and full sorted row sets,
including `match.id` and `recovery_family`.

The rebuilt installed artifact then passed the combined **32-case selection in
1.80 seconds**, exit zero. Four warnings concern unregistered pytest marks under
the isolated empty configuration. This was one affected installed run; the earlier
203-case native/admission selection was not repeated.

- [Installed log](</home/brunner56/agentdecompile-deliverables/2026-09-27-d3-destination-scope/installed-tests.log>) and [commands](</home/brunner56/agentdecompile-deliverables/2026-09-27-d3-destination-scope/commands.json>) retain actual results and execution identities.
- [Package report](</home/brunner56/agentdecompile-deliverables/2026-09-27-d3-destination-scope/package-report.md>) records 602 wheel members: 597 unchanged from accepted `.15`, two reviewed product overlays and three generated members. No members were added or removed; all 42 UI assets are unchanged.
- [Independent artifact review](</home/brunner56/agentdecompile-deliverables/2026-09-27-d3-destination-scope/independent-artifact-review.md>) verified installed bytes, wheel RECORD, 56 observed installed product-module origins, all 42 retained fixture hashes and exact archived product/test/fixture inputs. Broader release behavior is inherited from `.15`, not newly rerun.
- [Source/contract report](</home/brunner56/Documents/AgentDecompile-D3-destination-scope-report.md>) retains pre-task hashes, separate source attempts and the semantic/execution reviews.

Wheel SHA256:
`8350bb2cb99bf630cfe88e5fd2d888ab4b88703c95c15261d6afe8ecc8d9e5e5`.

Source/tests/reproduction archive SHA256:
`833b16f07f0968f1db067a7396b2989b75dde500dc7047817f99e84c3c9a7014`.
The 623-member archive contains the exact two product files, four test files and
committed cascade fixture. Deliverables and the retained accepted-base copy are on
NVMe to avoid repeated large artifact reads from MyBook.

## Limits and continuation

Export refusal establishes no output and unchanged identities/stored basis hashes,
not byte-for-byte database immutability. Historical data correction and authorized
rebaseline remain separate work. No real corpus, service, Ghidra, Wine or game was
operated, and no operational activation is claimed.

The inherited `.15` process-local 128-key watch limit remains. The next implementation
is the already-reviewed durable continuation design: persistent attempt budgets,
finite discovery/scan epochs, cursors, inherited output ownership through writing
descendants and session-cleared catalog generations. The full session goal remains
active.
