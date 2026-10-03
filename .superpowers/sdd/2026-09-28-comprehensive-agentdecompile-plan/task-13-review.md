# Task 13.1 review

## Spec compliance

**Issues found — bounded slice needs one lifecycle integration fix.** The committed-source reconciliation and preservation requirements are supported by the supplied two-parent package and manifest, but the combination of exact-child monitoring with donor reconciliation can permanently consume admission capacity after the exact child has exited. This violates the requested semantic integration of those ownership mechanisms (brief item 4). U13 itself remains open, correctly recorded in `docs/plans/agentdecompile-living-plan.md:23` and `docs/plans/agentdecompile-todo.md:25`.

Review basis: BASE `527b847a8b27a20edd759803325e3e119a35a38e`, HEAD `b871b845`, committed donor `2595ef42efc04df9869d81b3f6e4f090729fe4bc`; full `task-13-final-review.diff`, supplementary `task-13-retained-local-delta.diff`, brief, implementation report and source-reconciliation inventory. This is a scoped integration review, not a re-review of all 423 donor commits.

## Strengths

- Matcher preservation is substantive: histogram hashes are excluded from anchor authority, quarantined sources remain excluded from later stages, and the incremental destination set is maintained (`src/agentdecompile_recovery/corpus/match_store.py:600`, `:617`, `:628`, `:700`, `:751`, `:898`, `:1101`). The retained weak-versus-byte regression is adapted to content-hash build identities (`tests/test_match_evidence_fusion.py:23`).
- Identity propagation preserves the local fixed-point invalidation while constructing every new quarantine token through the donor hash-token helper. Conflict writes retain destination-binary scoping (`src/agentdecompile_recovery/corpus/propagate.py:223`, `:247`, `:257`, `:300`, `:305`, `:321`). The donor deterministic ordering and ambiguity-refusing legacy dedupe survive in the full package.
- Store integration preserves migration-owned atomic commits and connection failure closure instead of restoring the obsolete unconditional initializer (`src/agentdecompile_recovery/corpus/store.py:189`, `:191`, `:343`). `currentStage` is retained alongside donor public fields (`src/agentdecompile_recovery/corpus/dashboard/preparation.py:320`).
- The retained AtlasApp and exchange fixes have the original local blob identities. All 23 regular-file integrated blob IDs in the report were independently recomputed against current bytes and matched; the full package has 751 diff paths and no tracked deletion headers. The three excluded untracked capability files are absent here. These checks support preservation without asserting a fresh donor-working-tree audit.
- The mounted Vite root remains WorkstationApp (`src/agentdecompile_recovery/corpus/dashboard/frontend/src/main.tsx:6`), its base remains `/react/` (`frontend/vite.config.ts:45`), and static/package asset declarations remain present (`pyproject.toml:137`). No parallel frontend root or backend is introduced by the retained delta. Master-plan blob identity matches the donor manifest; living evidence and todo keep delivery acceptance open (`docs/plans/agentdecompile-living-plan.md:21`, `:23`, `:73`; `docs/plans/agentdecompile-todo.md:25`).

## Important finding

**[P1] Distinguish an active exact-child monitor from a completed monitor with uncleared descendants.**

Location: `src/agentdecompile_recovery/corpus/dashboard/actions/jobs.py:1430` and `:1465` (introduced integration logic); related retained contracts at `:735`, `:882`, `:909`, `:1510`, and executor return at `:2026`.

Source-derived reproducing sequence, with no runtime execution:

1. A qualified job consumes a worker slot and launches a child. Termination attempts leave that exact child alive, so `_default_executor` invokes `on_unresolved`; `_wait_for_process_owner` marks the job `cancelling`/`quarantined` and holds its worker and resource claims (`:1474–1495`).
2. The exact child subsequently exits. The monitor returns normally after observing that handle's exit, but a descendant still occupies the admitted session. `_default_executor` therefore returns the unresolved marker at `:2029–2030`.
3. `_run` mistakes that marker plus `cancelling` for an interrupted/still-unresolved exact-child monitor. It leaves `finished_at=None` (`:1430–1433`) and skips `_release_admission_locked` (`:1465–1466`), then its thread exits. No observer remains to notice later descendant clearance. The counted worker slot is never decremented.
4. For cross-place, the exact `executionOwner`, generation and duplicate lease are retained after the runner exits, which is the correct evidence/resource preservation. However, donor reconciliation rejects the current `cancelling` status as `live_executor_terminal` missing (`:735–736`). For other qualified jobs, reconciliation also requires a committed terminal release and terminal live status (`:882–883`, `:909–910`). Neither release implementation accounts for the stranded worker count (`:830–845`, `:945–958`). Thus later descendant exit cannot recover this state through the retained path. Enough instances exhaust `MAX_CONCURRENT`, blocking unrelated work as well.

Smallest safe correction: distinguish exact-handle monitoring state from session resource quarantine. Once the monitor has positively observed exact-child exit and `_run` is exiting, release the worker slot exactly once and record a terminal executor outcome while retaining quarantined resource keys, execution identity, generation and lease until the donor clearance/reconciliation contract authorizes their release. Existing `_release_admission_locked` already decrements worker capacity before refusing to drop quarantined resource maps (`:1510–1514`). Do not replace session clearance with child exit. A genuinely interrupted monitor with no child-exit observation must continue retaining ownership, with an explicit observer/reconciliation handoff rather than being misrepresented as an active thread forever.

Regression source should cover the integrated sequence above: monitor observes child exit, session remains occupied, runner returns, unrelated worker capacity is restored while resource claims stay held, and cross-place reconciliation becomes eligible only after fresh whole-session clearance. The existing `tests/test_job_owner_lifetime.py:134` fake executor returns plain terminal output immediately after the callback and does not exercise this combined path. Its separate interrupted-monitor case is not evidence for descendant clearance.

## Assessment

**Task quality: Needs fixes.** One Important lifecycle defect; no Critical finding. No other actionable integration finding was established in the reviewed retained delta.

**Cannot verify from this review:** actual merged software behavior; redirect selection/query/fragment compatibility; installed static usefulness without Node; hashed-asset staging/atomic index/old lazy-chunk retention; live source/reloader identities; runtime/platform/whole-image acceptance; or donor dirty-working-tree preservation after the historical inventory. Git ancestry/safety refs and unchanged donor-only blobs are represented by the supplied package/manifests, not independently re-enumerated with Git. KTD1–KTD5 show no new scoped source contradiction, but broad donor implementation correctness is outside this gate.

Checks performed: read-only diff/source inspection and regular-file blob hashing. Changed files were read outside diff context only where job lifecycle hunks ended mid-function, to trace the named monitor/reconciliation/worker-accounting risk; unchanged root/config/package files were checked for the named duplicate-root/package-boundary risk. No tests, builds, repository imports, runtime code, service operations, subprocess recovery, repeated AST checks, subagents or Git commands were run. Only this review report was written.
