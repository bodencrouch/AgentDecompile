# Task 13.1: committed source reconciliation report

Date: 2026-10-02. Status: **DONE_WITH_CONCERNS for bounded source reconciliation; U13 remains open.** No unit, installed-consumer or live acceptance is asserted.

## Exact history and ownership

- Worktree: `/home/brunner56/.codex/worktrees/6e95/AgentDecompile`; branch `codex/review-identity-workbench-fixes`.
- Original local tip: `527b847a8b27a20edd759803325e3e119a35a38e`; shared ancestor `a8b6d2faf8a71b633fd5dedfd07cc493ee250536`.
- Exact committed donor: `2595ef42efc04df9869d81b3f6e4f090729fe4bc`. No donor working files were ingested or changed.
- Planning import: `93217a5c488df3f3695ee8437732d86db2d40af5`. Explicit-path commit of the three already-copied files, each byte-identical to donor.
- Real ancestry merge: `0935dd5ca231334b2a80ce061d3bead450f7a510`. Parents: `93217a5c488df3f3695ee8437732d86db2d40af5 2595ef42efc04df9869d81b3f6e4f090729fe4bc`.
- Original review fixes `a804cf4b`, `a9b804aa`, `527b847a` remain ancestors. Safety refs: `refs/safety/task-13-local-20261002` and `refs/safety/task-13-donor-20261002`.
- Source trees: before `b240b84e2818d762cbff87f3807369fff1f1a4d9`, donor `c41eac4c1da258ec0ef20d2e6e8b128928ef6c02`, integrated `96e2c206e468abaf1a30840cb1fce3eb4d98186b`. The evidence-only report commit follows the merge, so this source basis is immutable.

[Source reconciliation inventory](source-reconciliation-report.md) retains the complete 754-path local-to-donor delta, 428-blob inventory, provenance and eight excluded donor owner-held paths. This report adds the exact resolved/local-preservation/package manifest below. Together with the immutable Git trees this is the complete before/donor/after source basis; unchanged donor entries keep the donor blob. There are no deleted tracked paths in the ancestry merge. The two apparent deletions in the raw local-to-donor comparison were local-only additions and remain retained.

Binding runtime evidence is reused from this turn's controller investigation, not re-observed by this implementation: 8080 health PID `2697197`, start `1790595674.5226107`, cwd `/home/brunner56/agentdecompile-nvme`; catalog receipt `564ff3819ece` loads modules beneath `/run/media/brunner56/MyBook/Workspaces/ai-projects/AgentDecompile/src`; loaded-source checkout HEAD `753d7fcea7580335e33533bf9aad693f6c5fe9b0`. Those source roots differ from this worktree. No copy, activation, restart, service operation or recovery admission occurred.

## All 13 conflict hunks and semantic disposition

Paths below are relative to `src/agentdecompile_recovery/corpus/`.

| File / hunk | Resolution and rationale |
|---|---|
| `match_store.py` 1 | Sorted BSim source iteration plus sticky quarantine refusal; preserve donor significance/mutual-best checks and tie-break order. |
| `match_store.py` 2 | Remove prior destination from incremental `taken` when quarantining; choose deterministic `min(destinations)` for advisory conflict display. |
| `match_store.py` 3 | Structural pairs exclude quarantined sources and sort eligible destinations. |
| `match_store.py` 4 | Inline residue excludes quarantined sources and uses sorted destinations with the existing `taken` set. |
| `propagate.py` 1 | Keep collision quarantine plus donor `dst_binary` in every conflict tuple/update. Both pre-selection and post-collision fixed-point rejection remain. Silent integration difference resolved: all newly created quarantine keys use donor `dependency_token(src_hash, src_addr)`, never legacy row IDs. Preserve destination-major hash order and ambiguity-safe legacy dedupe including exact numeric evidence. |
| `store.py` 1 | Retain inspected donor migration/read-only/backfill/rollback/close path. `migrations.apply_pending` owns per-migration atomic commits and `backfill_recovery_family` owns its update boundary. This subsumes local durable initialization and close-on-BaseException requirements; the obsolete unconditional SCHEMA/BEGIN path is not restored. |
| `dashboard/preparation.py` 1 | Union `currentStage` with donor `retryDecisions` and `objectiveBudget`; preserve the rest of donor public projection. |
| `dashboard/actions/jobs.py` 1 | Retain exact-child monitor callback, use donor's already-frozen execution cwd. |
| `dashboard/actions/jobs.py` 2 | Keep donor owner/clearance callbacks, cross-place generation/lease supervision and guarded dispatch; thread exact-child callback through normal, source-archive and cross-place executor calls. |
| `dashboard/actions/jobs.py` 3 | Use donor `resource_disposition` as the single reservation authority. Exact Popen monitor marks it quarantined and keeps the admission worker/locks until exit; interrupted monitoring keeps cancelling status and unfinished receipt. Donor session clearance and resource policy still gate release. Keep durable terminal persistence, external claims and lease cleanup. |
| `dashboard/actions/jobs.py` 4 | Union executor callback signatures; no competing executor implementation. |
| `dashboard/actions/jobs.py` 5 | Donor nonblocking pipe reader and bounded stop/join avoid the old buffered-read lock hazard; preserve guarded environment and inherited descriptor validation. |
| `dashboard/actions/jobs.py` 6 | Retain cancellation/deadline checks after early stdout EOF, exact-child monitor before final return, then donor session-clearance and exception cleanup. Child exit alone cannot clear surviving descendants. |

Additional silent jobs conflict resolved: remove the duplicated `ownershipUnresolved` dictionary key and independent boolean state; public ownership comes from resource disposition, `workerPid` from execution owner. Legacy retained receipts with only local ownership/worker fields are conservatively mapped to quarantine/identity-unavailable. Source-archive unresolved detection uses the donor shared parser, including executor callback/setup failures. Existing process-identity, clearance, persisted resource and cross-place generation contracts remain intact.

## Retained local fixes and regression-source reconciliation

All seven locally edited production paths are retained: matcher weak-hash exclusion/quarantine/incremental ownership; transitive identity dependency quarantine; store durable initialization; job exact-child lifetime and EOF cancellation; preparation `currentStage`; AtlasApp session state; exchange off-loop encoding and cancellation ownership.

`AtlasApp.tsx`, `exchange/store.py`, `tests/test_exchange_store.py` and `docs/verification/2026-10-02-code-review-fixes.md` are byte-identical to the original local tip. Donor did not change these from the shared ancestor. The local job regression file remains, with fake descriptor/nonblocking-reader/join and process/session-observer interfaces updated; its in-memory store includes donor external/cross-place reservation fields and asserts public reservation state. Matcher regression fixtures now supply deterministic per-build hashes for the donor dependency-token contract. No assertions were removed to accommodate an unexplained behavior difference. Earlier evidence remains historical; no tests were executed or claimed passing on this merge.

## Source verification actually performed

- Verified initial branch and original tip, donor/shared-base identity and planning-file SHA-256 equality before mutation.
- Real merge produced exactly five expected conflict files and 13 hunks; no additional conflict files or discarded paths.
- Parsed **407 changed Python files** with stdlib `ast.parse` only. No repository imports, runtime code execution, compilation or tests.
- Parsed the five conflict files for duplicate string keys in dictionary literals; none remain. Textual conflict-marker scan of changed source/doc/config files passed; index has no unresolved entries.
- Scoped whitespace checks for resolved sources, regression edits and plan updates pass. Broad merge whitespace check reports nine inherited donor issues in SVG/disassembly/native-oracle fixture files; their bytes are deliberately preserved. This is not a clean broad-lint claim.
- Compared original-local preserved blobs and donor-only package/source blobs; checked both ancestry parents and retained local commits. Exact manifests are below.
- Source-inspected `main.tsx` (only WorkstationApp is mounted), `/react/` Vite base, existing static fallback/routes, React redirect query retention/browser fragment inheritance comment, and package-data declarations. No route or package rewrite was necessary for this bounded integration.
- `vendor/ghidra` follows the committed donor gitlink; no submodule checkout/update or native build was run. Direct user's AGENTS constraints remain operative; donor changes only the implementation-reference command name in AGENTS.
- Updated the living plan, todo and plan hub, retaining all historical links and all unit checkboxes open. The master plan's source remains donor-identical.

## Limits and next concrete missing predicates

This is source reconciliation only. It does not prove the merged behavior, compatibility redirects, deployment safety or a successful software acceptance run. Swap pressure and current mission restrictions prohibit tests, builds, imports and runtime admission. No push or PR/publication occurred.

1. Independent review of this exact merge and its five conflict resolutions; then separately authorized positive/refusal software verification including early-EOF escalation, child-monitor interruption, descendant/session clearance, transitive hash-token quarantine with destination isolation, weak-hash refusal and committed migration reopen/failure-close behavior.
2. U13 selection preservation for `window=wb-*`, `binary_hash`, `function_id`, `project_id`, query and fragment requires browser receipts. Static usefulness without Node requires installed consumer observation. Source presence is insufficient.
3. U13 asset rollout remains open: stage new hashed assets first, switch index atomically last and retain old lazy chunks. Existing Vite `emptyOutDir: true` is build configuration, not evidence of a safe installed rollout.
4. Serving source/revision and standalone in-process reloader qualification with unchanged process/state identities remains open. This worktree is not the observed serving source root.
5. Next missing source slice is U25/U28 V5/R6: independently qualify cave producer/image/decoder/policy/generation evidence and bound canonical nesting depth. Existing cave inventory/receipts do not prove producer authority or authorize runtime mutation.
6. U1/U21 accepted-source adapter still needs immutable exact target/source/version/receipt/dependency/policy binding and failed/stale/unavailable handling. Retained matrix source truthfully leaves verified provider disconnected. Non-export/non-PE identity qualification remains separate.
7. All installed/live/runtime/platform/publication and fresh whole-image predicates remain open; neither finished jobs nor imported source close them.

## Exact local/resolved/package file manifest

Each cell records Git mode, object type and exact blob/gitlink ID. `absent` records a genuine missing entry in that tree. Full donor delta inventory is linked above; every unlisted imported path is donor-identical.

| Path | Before local | Committed donor | Integrated source |
|---|---|---|---|
| `AGENTS.md` | `100644 blob 0405f7af280c874099540cfd2cb9eba146dea2b0` | `100644 blob 46961df414ecbcc03e5dd7e439343d25fa45bc95` | `100644 blob 46961df414ecbcc03e5dd7e439343d25fa45bc95` |
| `docs/plans/2026-09-28-comprehensive-agentdecompile-plan.md` | `absent` | `100644 blob 5763c06b70905d383d4ce493e41274889fdcc76f` | `100644 blob 5763c06b70905d383d4ce493e41274889fdcc76f` |
| `docs/plans/README.md` | `100644 blob 9a8008310ec47b4d21989268fc41d0d219e6241e` | `100644 blob fe71ff43bd0c59f4ee6633bd3e80fddca059a38d` | `100644 blob 10d9d22759a76034cffe4341da327c7bf726e789` |
| `docs/plans/agentdecompile-living-plan.md` | `absent` | `100644 blob b044dde4b3973b07e77d3f50e7eaff8a69343635` | `100644 blob edff3b25d72c6a79be1af00cc65383ffdd53e5fb` |
| `docs/plans/agentdecompile-todo.md` | `absent` | `100644 blob 9ceb2cb507856d17489bd3fead6143e50379e433` | `100644 blob ebb0b51c7b67cdd77c67d6f1ac2fc6ce560c7188` |
| `docs/verification/2026-10-02-code-review-fixes.md` | `100644 blob 3d67e97e84a52c9c57a807dc7defc0cd5188c9f0` | `absent` | `100644 blob 3d67e97e84a52c9c57a807dc7defc0cd5188c9f0` |
| `pyproject.toml` | `100644 blob db0c3d7077f6492f5ee06856f430a3d350f82932` | `100644 blob b2a6d54f008c98ab98a88186b454bbc2881200d8` | `100644 blob b2a6d54f008c98ab98a88186b454bbc2881200d8` |
| `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py` | `100644 blob 36d03025d2b25c1fe38a1a0496ba693078cf1b42` | `100644 blob 28560a5d024c85fd04b1e6c4f3e07351b0387284` | `100644 blob 6e0935487e78721925840d4a1471a305c70b289b` |
| `src/agentdecompile_recovery/corpus/dashboard/frontend/src/AtlasApp.tsx` | `100644 blob 39e863a65ae71408723b3816622d181cf5a0f561` | `100644 blob 9a0df3f1b8f2c54e389ecef580780fe63395a21d` | `100644 blob 39e863a65ae71408723b3816622d181cf5a0f561` |
| `src/agentdecompile_recovery/corpus/dashboard/frontend/src/main.tsx` | `100644 blob 58c7d5853344b35214968c236fb79ebe9e830d73` | `100644 blob 58c7d5853344b35214968c236fb79ebe9e830d73` | `100644 blob 58c7d5853344b35214968c236fb79ebe9e830d73` |
| `src/agentdecompile_recovery/corpus/dashboard/frontend/vite.config.ts` | `100644 blob ed12835fd70e63d5a4ac979de0c66d7e539eb40d` | `100644 blob ed12835fd70e63d5a4ac979de0c66d7e539eb40d` | `100644 blob ed12835fd70e63d5a4ac979de0c66d7e539eb40d` |
| `src/agentdecompile_recovery/corpus/dashboard/preparation.py` | `100644 blob cc5bf323a969a1aaf07822327a19042f2c174ec8` | `100644 blob a01e59b4bff9440bc4170870f951b1cbd6f0feff` | `100644 blob 04214db06399bb34fc910a88c4ee1f9916e681a5` |
| `src/agentdecompile_recovery/corpus/dashboard/react_api.py` | `100644 blob 97816caba83e3c03a8c0c5c5c6037d233bcbee15` | `100644 blob 97816caba83e3c03a8c0c5c5c6037d233bcbee15` | `100644 blob 97816caba83e3c03a8c0c5c5c6037d233bcbee15` |
| `src/agentdecompile_recovery/corpus/dashboard/router.py` | `100644 blob 4bfd436f3f31dfa0030747c4b63626fc580182e4` | `100644 blob 8ebc32502f9d45419a82d4df4c7896db04c1d050` | `100644 blob 8ebc32502f9d45419a82d4df4c7896db04c1d050` |
| `src/agentdecompile_recovery/corpus/match_store.py` | `100644 blob 0fc174b5a044668db5e1582451fd72b43448696b` | `100644 blob efda5052f1a5dfe246fd4fd2508a1763de62a2e6` | `100644 blob 35da5baaf9e8e76d62a0868e107671f73a19e1a0` |
| `src/agentdecompile_recovery/corpus/propagate.py` | `100644 blob 811bb0e4a07f187df5f09c97bcd034da4b12d500` | `100644 blob 84f28239694b579f500b224175d58e3c81e0f3d7` | `100644 blob db8ec4fb343ed0b1f9bd327e3ac3c55e80834a04` |
| `src/agentdecompile_recovery/corpus/store.py` | `100644 blob 3df727376920a390c1cc623a3df0b50ed6753f9b` | `100644 blob 32ab1d5a7d75ad1c54cca1fe95bfefba128aafc4` | `100644 blob 32ab1d5a7d75ad1c54cca1fe95bfefba128aafc4` |
| `src/agentdecompile_recovery/exchange/store.py` | `100644 blob 5f8d3974dc6eddf4872376972ec778a15c67a8e8` | `100644 blob 083451282d403225419e1f9c871dbd53398f3636` | `100644 blob 5f8d3974dc6eddf4872376972ec778a15c67a8e8` |
| `src/agentdecompile_recovery/unified_pages.py` | `100644 blob 6a2c5db3b9034c0ce6bbc58007f59677f6dbbc23` | `100644 blob 6a2c5db3b9034c0ce6bbc58007f59677f6dbbc23` | `100644 blob 6a2c5db3b9034c0ce6bbc58007f59677f6dbbc23` |
| `tests/test_exchange_store.py` | `100644 blob d89dedd9485c8a164e0a288f6cd9d8ebb7f9525d` | `100644 blob 2ea3676c696f0a4f09112aecac8bd87e5a4e0851` | `100644 blob d89dedd9485c8a164e0a288f6cd9d8ebb7f9525d` |
| `tests/test_job_owner_lifetime.py` | `100644 blob 0a291d8db192ff616fe1f4e6564f5f35ff287665` | `absent` | `100644 blob eccc28f754e0964086d93e79ff9cee45ed950097` |
| `tests/test_match_evidence_fusion.py` | `100644 blob f845145def95c2d5f41bf0c3a0251852085f8ee2` | `100644 blob f76b286f59d835a68c8e21467edefb67fc69352e` | `100644 blob d9d771b292ec6e23c41ed75ed40e17dca1551506` |
| `vendor/ghidra` | `160000 commit 2035b8153afaf7ce2edde24a2c80b62bbcf5127f` | `160000 commit 5a6cd6929690110e804194825b0424e0d8545725` | `160000 commit 5a6cd6929690110e804194825b0424e0d8545725` |

## Fix round 1 — separate executor capacity from resource quarantine (2026-10-02)

Review basis: `b871b845`; finding P1 in [task-13-review.md](task-13-review.md). The initial reconciliation incorrectly treated a returned exact-child monitor plus occupied descendant session as an active executor: its dead runner retained worker capacity and nonterminal status, blocking later cross-place reconciliation. This appendix supersedes the initial report's statement that an interrupted monitor keeps unfinished executor status/capacity; **resource ownership remains held, executor capacity does not**.

Bounded production change: `_run` now records terminal executor status/time on returned or failed execution, including interrupted observation. Its final admission release runs once as the runner unwinds, using the existing helper's decrement-before-quarantine behavior; later resource repair never decrements worker capacity. The final release also survives terminal-persistence and lease-borrow unwind exceptions. Quarantined resource maps, execution owner, cross-place generation and duplicate physical lease remain intact until the existing qualified clearance/reconciliation contract permits release. No replacement PID is adopted and no child-exit observation is promoted to session clearance. An interrupted exact-child monitor records an explicit `resource reconciliation required` handoff in the retained job diagnostic; ordinary exception/BaseException unwind leaves terminal executor status rather than a phantom active thread. This introduces no second ownership authority or broader admission refactor.

Regression source only: `test_job_owner_lifetime.py` now distinguishes positive child exit with clear session, positive exit with occupied session, and monitor interruption. It preserves an unrelated counted worker, checks the terminal receipt and checks that unresolved identity/Ghidra resource maps remain held. The existing cross-place lifecycle fixture adds a two-case integrated catalog admission → real monitor → terminal receipt → occupied-session refusal → later fresh-session reconciliation source scenario. It checks retained owner/generation/lease, restored capacity exactly once, absence of the former live-executor refusal, refusal while session occupied, and qualified release only after a fresh clear observation. Child execution/session observations are controlled fixture seams; this is not live-process proof.

Verification performed: stdlib `ast.parse` of exactly the three changed Python files, duplicate dictionary-string-key source checks, manual source tracing through monitor/runner/release and cross-place eligibility/repair, and `git diff --check`. All passed as source checks. **No tests, test modules, project imports, builds, services or runtime operations were executed.** The two covering regression files remain unexecuted. The existing parent runtime/source binding remains inherited evidence; no activation claim. Independent scoped re-review is required before the next implementation task; all previously open U13/installed/live acceptance predicates remain open.

Fix source manifest (before blob at `b871b845`, after Git blob and SHA-256):

| Path | Before blob | After blob | After SHA-256 |
|---|---|---|---|
| `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py` | `6e0935487e78721925840d4a1471a305c70b289b` | `ade37d9434812b699e9469d2bf2efe0716a1892c` | `76e5a1fc59df9e62bb559f5016b660297177ee66af92b63a415fee82c6d9045b` |
| `tests/test_job_owner_lifetime.py` | `eccc28f754e0964086d93e79ff9cee45ed950097` | `7d1a70ca478ce82ca6fe7aba4fe4504d47a246f6` | `c1bb25f7bfdfb534a251d217a4b14353c8007bfee8406d9ce17561eeeecceb19` |
| `tests/test_cross_place_catalog_lifecycle.py` | `55c1c318f7a39a3603904d2bc955bddb4911499d` | `eec426afd751f353d5d40ce105bcbcb1ded1f7e1` | `1704ccd03c4504e55f9938df1b458eb1a9f75ba4abb7910feb434da403682450` |
