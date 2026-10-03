# Task15.1 fix round 1 independent review

Reviewed the supplied `task-15-fix-r1-review.diff` for base `ccd9b63af57d418cf26842584444e2a471d4348f` and head `7eb844b374ce254fe9214bad1b589e5e530fb057`, against the original brief, complete adopted shared-selection contract, original review, fix brief, and appended correction receipt.

**Spec verdict: changes required. Quality verdict: changes required.** Original Important I1 and I3 are addressed by source inspection. I2's session-response cancellation is corrected, but its unpinned restoration/preview path still cancels itself after inventory discovery. Minor M1 remains deferred and is not a blocker in this round.

## Original finding disposition

| Finding | Source assessment |
|---|---|
| I1: A-to-B open cancels itself on an intervening render | Addressed for the reported sequence. `resetTabState(nextLocator)` installs B's pending dossier locator synchronously (`workbench-app.js:4008–4024,4592`). Render honors an explicit locator even when empty (`:3489–3494`), so the old saved A session cannot restore A into the pending target. Later open/selection still retires the captured generation. The added deferred B-open and B-then-C cases inspect actual persistence/context closures, without claiming execution. |
| I2: background discovery cancels bootstrap | Partially addressed. The separate navigation generation prevents corpus/hash enrichment alone from rejecting the sessions response (`:3508–3521,4147–4162`). Explicit selection/open still advances navigation ownership. However, unpinned restoration uses a stale identity lookup before starting its preview; see Important R1 below. |
| I3: post-action detail refresh retires its inventory refresh | Addressed. One refreshed intent is created before both `loadFuncs` and `readSelection` (`:5453–5458`), after the original action intent passes admission. Neither read creates another selection intent. The added synchronous rename cases cover list-first/detail-first completion and inspect actual submitted context and final rows without a job-poll fallback. |
| M1: out-of-range Listing focus index | Explicitly deferred per fix brief. Not expanded, reclassified, or used to require another fix round. |

## Critical

None identified within this narrow review.

## Important R1 — unpinned bootstrap still retires its own project preview

Primary changed-line reference: `src/agentdecompile_recovery/corpus/dashboard/static/workbench-app.js:4173–4177`. Related source: `:3532–3537` (`setSlug` captures binaries), `:3519–3522` (render identity retirement), `:3885–3898` (preview admission), and `:4235` (bootstrap effect dependencies). Confidence: high, based on the explicit closure and continuation chain; no runtime reproduction is claimed.

The bootstrap effect keeps the first render's `setSlug` callback, which closes over the initial empty `binaries`. Its dependencies do not refresh that callback when inventory arrives. The new navigation fence permits the following ordinary startup sequence:

1. Open the dashboard without a pinned slug/binary/program. The binaries request resolves with saved project S and a supplied content hash; render that inventory before sessions resolves.
2. Sessions resolves with S's locator, projectSlug, and program. The restored-session branch calls its captured initial `setSlug(S)`. That callback finds no S in its old empty array and sets `targetRef.current.content` to an empty string.
3. The branch installs the pending locator and calls `loadPreview` with a newly captured intent containing that empty content identity.
4. The next render derives S's real hash from the already-loaded inventory, sees a different target key, and retires the new intent. The deferred valid inspection response then fails `loadPreview.currentRead()` and is discarded.

Sessions and the locator can now appear restored, but the dossier remains only `{locator}` and the normal inspected project metadata/program list is never admitted. This is still bootstrap invalidating its own restoration continuation without a later user intent. The same issue can occur when preview remains pending until the first post-session render even though identity discovery completed earlier.

The new tests do not cover this route: `StaticSelectionIsolation.test.ts:49` hardcodes `?slug=project-slug&program=game.exe` for every case, so bootstrap skips `setSlug` and `setProgram` restoration. The bootstrap assertions after preview completion only check the locator, which already exists in the pending dossier and does not demonstrate acceptance of the inspection result.

Suggested correction: ensure the restored target and preview intent use the latest discovered inventory identity even from the bootstrap continuation, or give the project-preview continuation appropriate navigation ownership while preserving strict captured identity for selected evidence. Do not remove current-evidence masking or allow a later user/open intent to lose. Author an unpinned startup case with inventory/hash settled and rendered before sessions, a render after sessions but before inspection, and an assertion on accepted dossier/preview metadata rather than merely the pending locator. Retain later-user supersession coverage. This is a remaining variant of original I2, not a request for broader navigation work.

## New independent findings

No separate new Important defect was identified in the pending-locator or common post-action-intent changes. Existing selected-evidence key checks, stale-response masking, action-context capture, and later-intent refusal remain present in the inspected paths. This does not certify all background effects or all App operations.

## Review scope and limitations

Read the assigned six artifacts and bounded source around the changed navigation/effect/refresh paths, `loadPreview`, target setters, bootstrap dependencies, function-list and deep-link effects, and the dedicated/shared hook harness. These reads were to follow the three original findings and their corrections; no broad branch audit was repeated. Truncated combined output was recovered through bounded direct reads of the relevant application and fixture ranges.

The added harness runs only the named bootstrap effect, deliberately disables other App effects, and uses explicit renders/microtask settlement. Its memoized callbacks better model bootstrap dependency stability, but neither its source nor this review proves real React scheduling, StrictMode, other effect interactions, DOM behavior, browser delivery, or installed/live acceptance. No authored case was executed, collected, imported, or typechecked. The implementer's reported syntax check was not rerun.

Wrote only this review document. No source changes, Git operations, subagents, tests, collection, builds, imports, typechecks, database access, runtime/live/process checks, provisioning, or publication were performed. All behavioral and broader U15 acceptance remains open.
