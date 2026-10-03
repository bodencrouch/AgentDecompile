# Spec Compliance

- ❌ Issues found. The core stale-response boundary is implemented, but new failures in project-open admission, initial restoration, and post-action refresh violate the required preservation of existing ingress and catalog behavior. See Important findings 1–3.
- ⚠️ Behavioral, real React effect/DOM scheduling, installed-consumer, focus/scroll, and full-U15 acceptance remain unverified. The fixture explicitly omits effects (`src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/StaticSelectionIsolation.test.ts:4`); source-authored cases are not passing-test evidence. This review did not execute or collect them.
- Scope is otherwise appropriate: the review package changes only the static App, one dedicated regression source, and the implementation report. It does not expand into backend, React application, independent SymbolTree cache repair, draft/history, or batch ownership work.

# Strengths

- `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:3568`: evidence is projected through the current intent during render, so an old packet is not temporarily exposed under a new primary selection while an effect catches up.
- `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:3663`: the admitted evidence commit separates requested address from the returned function center and records last-decompile provenance from the evidence packet rather than the later selected label.
- `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:3735`: evidence retries and diagnostic lookups retain the originating intent; a stale response cannot start a fresh fallback chain.
- `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:5322`: the live context getter reads current target/primary refs, including the event-turn interval before another render. `:7072` also refuses SymbolTree callbacks without matching provenance while keeping its separate cache repair out of scope.
- `src/agentdecompile_recovery/corpus/dashboard/frontend/src/workstation/StaticSelectionIsolation.test.ts:1`: the fixture exercises actual App closures and action bodies and accurately discloses its scheduler limitations.

# Issues

## Critical

- None found.

## Important

1. **Opening a different project from an existing tab invalidates its own operation.** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:4586–4594` resets the tab, captures `openGeneration`, and waits for inspection. Reset clears the dossier and sets the ref locator to empty (`:4004`) without replacing the current session. On the intervening render, `renderedTarget` falls back to that old session's locator (`:3489–3490`); the render comparison calls `retireSelection` again (`:3513`). The inspection response consequently fails its generation check even though the user made no subsequent selection. Opening project B from a tab containing project A silently stops before admission. Keep the pending target/reset identity consistent with the rendered state, or separate operation ownership from reconciliation of the old session. Author a successful A→B open case with a render while inspection is deferred, as well as the actual user-supersession refusal case.

2. **Bootstrap restoration is cancelled by background identity discovery.** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:4144–4157` captures the selection generation and starts corpus/inventory reads before accepting the session response. If the corpus identity resolves first, `setCorpusIdentity` (`:3599`) changes `targetKey`; the next render retires selection (`:3513`) and the session response is discarded. A pinned slug gaining its inventory hash has the same effect. This requires no user interaction, leaves saved tabs unrestored, and has no retry. Bootstrap cancellation must distinguish a newer user/open intent from the bootstrap's own discovery of identity. Add an effect-capable deferred-order case in which corpus/inventory settle before sessions, plus a case proving a real subsequent user intent still wins.

3. **Every post-action inventory refresh is immediately made obsolete.** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:5451–5454` starts `loadFuncs` with `actionIntent`, then immediately calls `beginSelection` for the detail refresh. That retires `actionIntent` before the function-list fetch/body continuation can complete, so `loadFuncs` always rejects its own result through `currentRead` (`:3626`). A successful rename/decompile no longer updates the function list through this existing action completion path; a separate job poll or manual refresh is not a substitute, especially for synchronous actions. Create the refreshed intent first and share it between both reads, or scope the inventory refresh independently to the captured concrete target. Add a completed action→updated function-list assertion.

## Minor

1. **Preserving focus also needs an out-of-range fallback.** `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:2701` removes the focus-index reset entirely. If a refresh replaces a longer listing with fewer rows while `focusIdx` points beyond the new length, every rendered row has `tabIndex=-1`, because the existing renderer assigns the tab stop only to `idx === focusIdx`. Preserve the index when it still exists, but clamp it when the row set shrinks. This is a new local refresh consequence, not a request to close the separate full accessibility task.

# Assessment

**Task quality: Needs fixes.**

The captured read envelope and keyed projections are a sound improvement. The broad setter conversion nevertheless couples render-derived identity, user intent, and operation continuation ownership in a way that cancels legitimate work; the three concrete failures above must be fixed before accepting the bounded source predicate.

# Review checks and limits

- Reviewed the supplied brief, adopted `next-shared-selection-contract.md`, report, and exact package for `cc4524075cacdf25a1ae667ab97c92b1f740656c..ccd9b63af57d418cf26842584444e2a471d4348f`, including commit/stat/full diff. One initially truncated tool output required bounded recovery of the omitted diff section; no Git diff was regenerated.
- Named focused checks outside diff context: session setter/restore ordering (`persistSessions`, `patchActiveSession`); actual effect callers of `loadFuncs` and deep-link selection; import/remove inspection ownership (`applyProjectInspect`); catalog context defaults and confirmation/batch call sites; and remaining synchronous ensure callers. These were read-only source checks of the named ingress/context risks, not a broader repository audit.
- Read the remainder of `ListingRows` because its changed effect hunk was cut off before the dependency list and row rendering; this establishes the focus-index consequence and the local reader dependencies.
- No tests, test collection, builds, typechecks, proof scripts, project imports, browser/runtime/DB/process/catalog/service operations, Git mutation, publication, or source changes were performed. Only this review document was written. The implementer's reported `node --check` result was not rerun.
