# Task15.1 fix round 2 independent review

Reviewed the exact `task-15-fix-r2-review.diff`, base `7eb844b374ce254fe9214bad1b589e5e530fb057`, head `d2e0ccc2ca3a63fa12a0686f39527f1f69535c06`, with the round-2 brief and appended correction receipt. The original brief/contract and round-1 review remain the scope boundary.

**Source spec verdict: pass for this bounded correction. Source quality verdict: pass for this bounded correction.** Remaining Important R1 (the unpinned variant of original I2) is addressed. Original I1/I3 retain their addressed source dispositions. No new Critical or Important finding was identified. Minor M1 remains explicitly deferred and nonblocking.

## Addressed R1

`src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:3346,3533–3540,3594–3600` introduces a stable inventory ref, updates it with the same list passed to the sole `setBinaries` writer, and resolves `setSlug` identity through that ref. The bootstrap continuation can retain the original callback without retaining the original empty inventory.

For the reported sequence—inventory/hash supplied and rendered before unpinned sessions arrive—the restored target now captures that known hash before creating its preview intent. The subsequent render computes the same content identity, so identity reconciliation no longer retires the preview solely because restoration used stale inventory. The ref is updated before the inventory state setter; no additional inventory writer was found in the focused source search.

The correction does not rewrite existing immutable intents or packets. `beginSelection`, `isCurrentIntent`, render-time evidence masking, preview generation/intent checks, mounted checks, and bootstrap navigation ownership are unchanged in the diff. Later user selection/open therefore retains its refusal boundary. The changed callback remains stable and no effect dependency is added that would remount bootstrap on inventory updates.

## Authored regression assessment

`StaticSelectionIsolation.test.ts:44–70` now permits an explicitly empty URL search and exposes actual binaries/dossier/preview projections. The new case at `:187–240` follows the previously missing route: render known inventory/corpus identity first, then restore unpinned sessions, render again while inspection remains deferred, and finally resolve inspection. The positive branch compares the actual dossier and preview to the inspected payload, including its kind/program metadata, rather than accepting the pending locator as sufficient evidence.

The paired superseded branch selects B after restoration but before inspection settles; it checks that the obsolete inspection stays unadmitted and B survives its own selected read. Earlier later-selection/later-open bootstrap cases remain, and pinned restoration now also asserts admitted dossier metadata. These are meaningful authored assertions against the actual App closures within the disclosed harness. They were not executed and are not passing-test evidence.

## Findings and limits

Critical: none. Important: none remaining in this correction scope. Minor M1: deferred as instructed; no additional fix loop requested for it.

This review read the assigned correction artifacts and bounded source around the inventory writer, stable slug setter, immutable intent boundary, bootstrap restoration, preview checks, and new regression cases. It did not repeat a broad branch/UI audit. The original pending-locator and shared post-action-refresh fixes were not modified by this round.

Wrote only this review document and preserved concurrent work. No source edits, Git operations, subagents, tests/collection, imports, builds, typechecks, database operations, runtime/live/browser/process inspection, provisioning, or publication were performed. The implementer's reported syntax check was not rerun. The named-bootstrap hook shim still omits other effects and does not establish real React scheduling, StrictMode, DOM/focus/scroll, installed delivery, or full U15 acceptance. All behavioral qualification remains separately open.
