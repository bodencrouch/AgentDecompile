# Scoped activity evidence and selection safety — 2026-09-27

Status: independently reviewed source, locked frontend build and verified isolated
development package. This implements part of L0.2–L0.5 in the
[September 22 program](../plans/2026-09-27-implementation-progress-and-live-track.md).
Live activation and browser acceptance remain open.

## Actual behavior and limits

The existing activity snapshot/SSE route attaches a bounded claim projection to
one unambiguously selected inventory target. Full candidate keys preserve distinct
source candidates at the same address. Both static Explorer and React Explorer/
Workstation Evidence views show three independent rows:

- Recorded region bytes, with a bounded current source-digest check. The stored
  bytes are not a fresh target comparison or compiler observation.
- A coherent historical PE export witness, explicitly target-not-rechecked.
  Source mutation does not erase this independent historical record.
- Unavailable placed-source contribution: this serving route has no trusted
  process-local reconstruction observation. Imported JSON cannot create one.

Every row has `accepted:false`. There is no combined accepted score. Selection
uses inventory identity and project/program/slug bindings, with contradictory or
ambiguous targets declining projection. Missing schema, malformed rows, unavailable
files and truncation are explicit. One invalid candidate does not erase its sibling.
The added passive path does not call lazy function observation or admit recovery.

SQLite is opened read-only with query and instruction bounds. Source files are
limited to 4 MiB each, with an 8 MiB shared source/receipt allowance; candidate and
binary-ID lists cap at 64. Source reads corroborate descriptor/path state before
and after observation. Receipt links are server-discovered, confined to approved
roots and hashed, but remain target/address references, not candidate proof or a
guarantee against later artifact replacement. Both views show incomplete coverage.

Static transport now rejects late old-target responses, protects newer stream
revisions, preserves same-scope library hydration when SSE arrives first, serializes
polls, and handles reset/restart. Late function inventories are also target guarded.
React's inspected-entity view no longer substitutes another selection's evidence
or resurrects a captured entity after its fresh snapshot removes it.

Schema and inherited basis/check time describe this conservative projection.
Separate machine-readable policy revision/currentness-basis metadata, fresh target
observation, trusted contribution-handle plumbing and durable re-admission remain
open. This is not the full three-positive-claims demonstration.

## Verification and package

Independent static review approved the frozen implementation after correcting
selection races, target ambiguity, malformed sibling handling and read-budget
accounting. Actual-function checks cover source mutation, forged flags, wrong
target/address, bounded reads, receipt links, the activity builder, both renderers,
SSE/HTTP ordering, reset/restart and target switching.

- Source backend: **8 passed**. Installed backend: **8 passed in 0.68 seconds**.
- Frontend: **12 passed**, including nine new and three adjacent display cases.
- TypeScript and locked Vite production build: **exit 0**; existing chunk-size
  warnings remain. No mounted-browser validation is implied.
- Package: `2.0.1.dev0+autonomy20260927.10`.
- Wheel SHA-256: `91fc725733f6ce70a04bd901276d67bb9aaf6a3c0b549f874c10df9ca5b99a1f`.
- All three changed backend/static package members and 21 rebuilt frontend assets
  match the approved source/build, wheel and isolated installation. Installed
  module origins and package version were asserted before running the backend cases.
- Provenance accounts for all 597 wheel members: 566 byte-equal members reused
  from verified `.9`, three reviewed source/static overlays, 21 locked frontend
  assets and seven generated metadata/version members. This is an explicit staged
  increment, not a claim that unrelated canonical dirty files were rebuilt.

Durable wheel, reviewed source/tests archive, review, logs, asset/source hashes,
installed-origin assertions and complete member provenance are retained under
`/home/brunner56/Documents/AgentDecompile-deliverables/2026-09-27-live-evidence/`.
The isolated build/install stage is `/dev/shm/ad-live-evidence-package-h30uohjt`.

No 8080 listener was present at preflight. No service, alternate port, game,
Ghidra or recovery job was launched or replaced. Actual static and packaged React
browser routes, current target transitions, receipt navigation and unchanged
serving process/state identity still require live qualification. M0 remains partial;
M1–M7 and terminal whole-image recovery remain open.
